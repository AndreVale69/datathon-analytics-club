from __future__ import annotations

import json
from typing import Any

from app.core.hard_filters import _distance_km
from app.models.schemas import HardFilters, ListingData, RankedListingResult
from app.participant.description_extractor import ExtractedFeatures


_W_GEO             = 0.60  # fixed geo share when geo is active
_W_SOFT_MAX_GEO    = 0.30  # max soft share when geo is active   → query_min = 0.10
_W_SOFT_MAX_NO_GEO = 0.90  # max soft share when geo is absent   → query_min = 0.10

# Number of active soft criteria at which soft_factor reaches 1.0 (full soft weight).
# Below this, the soft weight scales linearly and the surplus goes to query.
_N_SOFT_SAT = 5

_GEO_DEFAULT_RADIUS_KM = 10.0


def rank_listings(
    candidates: list[dict[str, Any]],
    soft: HardFilters,
    hard: HardFilters | None = None,
    query_similarities: dict[str, float] | None = None,
    extracted_features: dict[str, ExtractedFeatures] | None = None,
) -> list[RankedListingResult]:
    sims = query_similarities or {}
    feats = extracted_features or {}
    hard = hard or HardFilters()
    results = [
        RankedListingResult(
            listing_id=str(c["listing_id"]),
            score=_score(c, soft, hard, sims.get(str(c["listing_id"]), 0.0), feats.get(str(c["listing_id"]))),
            reason=_reason(c, soft, hard, sims.get(str(c["listing_id"]), 0.0), feats.get(str(c["listing_id"]))),
            listing=_to_listing_data(c),
            matched_soft_features=_matched_soft_features(soft, feats.get(str(c["listing_id"]))),
        )
        for c in candidates
    ]
    return sorted(results, key=lambda x: x.score, reverse=True)


def build_score_breakdown(
    listing: dict[str, Any],
    soft: HardFilters,
    hard: HardFilters | None = None,
    query_sim: float = 0.0,
    extracted: ExtractedFeatures | None = None,
) -> dict[str, Any]:
    hard = hard or HardFilters()
    w_query, w_geo, w_soft = _weights(soft, hard)
    q = max(0.0, min(1.0, query_sim))
    geo = _geo_score(listing, soft, hard)
    soft_s = _soft_score(listing, soft, extracted)
    score = round(w_query * q + w_geo * geo + w_soft * soft_s, 4)
    target = hard if _has_geo_target(hard) else (soft if _has_geo_target(soft) else None)
    dist_km = None
    if target is not None and listing.get("latitude") is not None and listing.get("longitude") is not None:
        dist_km = _nearest_target_distance(listing["latitude"], listing["longitude"], target)

    return {
        "final_score": score,
        "query_score": q,
        "geo_score": geo,
        "soft_score": soft_s,
        "weights": {
            "query": w_query,
            "geo": w_geo,
            "soft": w_soft,
        },
        "contributions": {
            "query": round(w_query * q, 4),
            "geo": round(w_geo * geo, 4),
            "soft": round(w_soft * soft_s, 4),
        },
        "distance_km": None if dist_km is None else round(dist_km, 3),
        "price_chf": listing.get("price"),
        "area_sqm": listing.get("area"),
        "rooms": listing.get("rooms"),
        "city": listing.get("city"),
        "matched_features": [
            feature for feature in (soft.features or []) if listing.get(f"feature_{feature}") == 1
        ],
        "missing_features": [
            feature for feature in (soft.features or []) if listing.get(f"feature_{feature}") != 1
        ],
        "matched_soft_features": _matched_soft_features(soft, extracted),
        "description_features": extracted.model_dump(exclude_none=True) if extracted else {},
    }


def _weights(soft: HardFilters, hard: HardFilters) -> tuple[float, float, float]:
    """Return (w_query, w_geo, w_soft) that always sum to 1.0.

    As soon as any constraint is active (geo or soft), semantic is fixed at 0.10.
    The remaining 0.90 goes entirely to geo+soft:
      - geo active: soft scales with soft_factor (up to _W_SOFT_MAX_GEO), geo takes the rest.
      - no geo: soft takes the full 0.90.
    With no constraints at all, semantic gets 1.0.
    """
    n = _count_soft_constraints(soft)
    use_geo = _has_geo_target(hard) or _has_geo_target(soft)

    if not use_geo and n == 0:
        return 1.0, 0.0, 0.0

    w_query = 0.10
    if use_geo:
        soft_factor = min(1.0, n / _N_SOFT_SAT) if n > 0 else 0.0
        w_soft = _W_SOFT_MAX_GEO * soft_factor
        w_geo  = 0.90 - w_soft
    else:
        w_soft = 0.90
        w_geo  = 0.0

    return w_query, w_geo, w_soft


def _score(listing: dict[str, Any], soft: HardFilters, hard: HardFilters,
           query_sim: float = 0.0, extracted: ExtractedFeatures | None = None) -> float:
    w_query, w_geo, w_soft = _weights(soft, hard)
    q      = max(0.0, min(1.0, query_sim))
    geo    = _geo_score(listing, soft, hard)
    soft_s = _soft_score(listing, soft, extracted)
    return round(w_query * q + w_geo * geo + w_soft * soft_s, 4)


def _geo_score(listing: dict[str, Any], soft: HardFilters, hard: HardFilters) -> float:
    lat = listing.get("latitude")
    lon = listing.get("longitude")
    if lat is None or lon is None:
        return 0.0
    target = hard if _has_geo_target(hard) else (soft if _has_geo_target(soft) else None)
    if target is None:
        return 0.0
    dist_km = _nearest_target_distance(lat, lon, target)
    if dist_km is None:
        return 0.0
    radius = target.radius_km or _GEO_DEFAULT_RADIUS_KM
    return max(0.0, 1.0 - dist_km / radius)


_HOUSE_CATEGORIES = {"Haus", "Villa", "Reihenhaus", "Doppeleinfamilienhaus",
                     "Mehrfamilienhaus", "Bauernhaus", "Terrassenhaus"}
_ROOFTOP_CATEGORIES = {"Dachwohnung", "Attika"}
_TERRACE_CATEGORIES = {"Terrassenwohnung", "Maisonette"}


# Maps each SoftFilters boolean field to the corresponding ExtractedFeatures field.
# Used by both _count_soft_constraints and _soft_score.
_BOOL_SOFT_TO_EXTRACTED: list[tuple[str, str]] = [
    # physical / structural
    ("furnished",        "furnished"),
    ("garden",           "has_garden"),
    ("rooftop",          "has_rooftop"),
    ("terrace",          "has_terrace"),
    ("cellar",           "has_cellar"),
    ("bathtub",          "has_bathtub"),
    ("view",             "has_view"),
    ("not_ground_floor", "not_ground_floor"),
    # interior / aesthetic
    ("bright",           "is_bright"),
    ("modern",           "is_modern"),
    ("good_layout",      "good_layout"),
    # neighbourhood / environment
    ("quiet",            "is_quiet"),
    ("near_lake",        "near_lake"),
    ("safe",             "safe_area"),
    ("good_schools",     "good_schools"),
    ("low_traffic",      "low_traffic"),
    ("green_space",      "green_space"),
    ("walkable_shopping","walkable_shopping"),
    ("good_transport",   "good_transport"),
    ("family_friendly",  "family_friendly"),
    ("playground_nearby","playground_nearby"),
]


def _count_soft_constraints(soft: HardFilters) -> int:
    """Count all expressed soft criteria (DB-verifiable + description-only)."""
    n = 0
    if soft.features:                           n += 1
    if soft.max_price:                          n += 1
    if soft.min_rooms:                          n += 1
    if soft.min_area:                           n += 1
    if soft.city:                               n += 1
    if getattr(soft, "min_bedrooms", None):     n += 1
    if getattr(soft, "min_bathrooms", None):    n += 1
    for soft_field, _ in _BOOL_SOFT_TO_EXTRACTED:
        if getattr(soft, soft_field, None):     n += 1
    return n


def _soft_score(listing: dict[str, Any], soft: HardFilters,
                extracted: ExtractedFeatures | None = None) -> float:
    """Average of per-criterion [0,1] scores for every expressed soft preference."""
    scores: list[float] = []
    cat   = listing.get("object_category") or ""
    rooms = listing.get("rooms")

    # ── DB-verifiable ─────────────────────────────────────────────────────────
    if soft.features:
        matched = sum(1 for f in soft.features if listing.get(f"feature_{f}") == 1)
        scores.append(matched / len(soft.features))

    price = listing.get("price")
    if soft.max_price and price:
        scores.append(max(0.0, min(1.0, 1.0 - price / soft.max_price)))

    if soft.min_rooms and rooms:
        scores.append(max(0.0, 1.0 - abs(rooms - soft.min_rooms) / soft.min_rooms))

    area = listing.get("area")
    if soft.min_area and area:
        scores.append(max(0.0, 1.0 - abs(area - soft.min_area) / soft.min_area))

    if soft.city:
        city = (listing.get("city") or "").lower()
        scores.append(1.0 if any(city == c.lower() for c in soft.city) else 0.0)

    # ── Category-proxied (improved by extracted when available) ───────────────
    if getattr(soft, "furnished", None):
        if extracted and extracted.furnished is not None:
            scores.append(1.0 if extracted.furnished else 0.0)
        else:
            scores.append(1.0 if cat == "Möblierte Wohnung" else 0.0)

    if getattr(soft, "garden", None):
        if extracted and extracted.has_garden is not None:
            scores.append(1.0 if extracted.has_garden else 0.0)
        else:
            scores.append(1.0 if cat in _HOUSE_CATEGORIES else 0.0)

    if getattr(soft, "rooftop", None):
        if extracted and extracted.has_rooftop is not None:
            scores.append(1.0 if extracted.has_rooftop else 0.0)
        else:
            scores.append(1.0 if cat in _ROOFTOP_CATEGORIES else 0.0)

    if getattr(soft, "terrace", None):
        if extracted and extracted.has_terrace is not None:
            scores.append(1.0 if extracted.has_terrace else 0.0)
        else:
            scores.append(1.0 if cat in _TERRACE_CATEGORIES else 0.0)

    # ── Numeric description-based ─────────────────────────────────────────────
    min_bed = getattr(soft, "min_bedrooms", None)
    if min_bed:
        if extracted and extracted.bedrooms is not None:
            scores.append(1.0 if extracted.bedrooms >= min_bed else
                          max(0.0, extracted.bedrooms / min_bed))
        elif rooms:
            estimated = max(0.0, rooms - 1)
            scores.append(1.0 if estimated >= min_bed else max(0.0, estimated / min_bed))

    min_bath = getattr(soft, "min_bathrooms", None)
    if min_bath:
        if extracted and extracted.bathrooms is not None:
            scores.append(1.0 if extracted.bathrooms >= min_bath else
                          max(0.0, extracted.bathrooms / min_bath))
        else:
            scores.append(0.0)

    # ── Pure description-based booleans (all via _BOOL_SOFT_TO_EXTRACTED) ─────
    for soft_field, ext_field in _BOOL_SOFT_TO_EXTRACTED:
        if soft_field in ("furnished", "garden", "rooftop", "terrace"):
            continue  # already handled with category fallback above
        if getattr(soft, soft_field, None):
            ext_val = getattr(extracted, ext_field, None) if extracted else None
            scores.append(1.0 if ext_val else 0.0)

    if not scores:
        return 0.0
    return sum(scores) / len(scores)


def _matched_soft_features(soft: HardFilters, extracted: ExtractedFeatures | None) -> list[str]:
    """Return soft field names where the user requested the feature AND the description confirms it."""
    matched: list[str] = []
    if extracted is None:
        return matched
    for soft_field, ext_field in _BOOL_SOFT_TO_EXTRACTED:
        if getattr(soft, soft_field, None) and getattr(extracted, ext_field, None):
            matched.append(soft_field)
    min_bed = getattr(soft, "min_bedrooms", None)
    if min_bed and extracted.bedrooms is not None and extracted.bedrooms >= min_bed:
        matched.append("min_bedrooms")
    min_bath = getattr(soft, "min_bathrooms", None)
    if min_bath and extracted.bathrooms is not None and extracted.bathrooms >= min_bath:
        matched.append("min_bathrooms")
    return matched


def _reason(listing: dict[str, Any], soft: HardFilters, hard: HardFilters,
            query_sim: float = 0.0, extracted: ExtractedFeatures | None = None) -> str:
    w_query, w_geo, w_soft = _weights(soft, hard)
    q      = max(0.0, min(1.0, query_sim))
    geo    = _geo_score(listing, soft, hard)
    soft_s = _soft_score(listing, soft, extracted)

    parts: list[str] = []

    # ── Dominant factor ───────────────────────────────────────────────────────
    contributions = {"query": w_query * q, "geo": w_geo * geo, "soft": w_soft * soft_s}
    dominant = max(contributions, key=contributions.__getitem__)
    if dominant == "query" and q >= 0.5:
        parts.append(f"Strong match with your search description ({q:.0%} similarity)")
    elif dominant == "geo" and geo >= 0.5:
        parts.append("Excellent location match")
    elif dominant == "soft" and soft_s >= 0.5:
        parts.append("Matches most of your preferences")

    # ── Location details ──────────────────────────────────────────────────────
    lat = listing.get("latitude")
    lon = listing.get("longitude")
    if lat is not None and lon is not None and (w_geo > 0 or _has_geo_target(hard) or _has_geo_target(soft)):
        target = hard if _has_geo_target(hard) else soft
        dist_km = _nearest_target_distance(lat, lon, target)
        if dist_km is not None:
            if dist_km < 0.5:
                parts.append(f"Within walking distance of target ({dist_km:.2f} km)")
            elif dist_km < 2.0:
                parts.append(f"Very close to target area ({dist_km:.1f} km)")
            else:
                parts.append(f"{dist_km:.1f} km from target area")

    # ── Soft constraint details ───────────────────────────────────────────────
    cat   = listing.get("object_category") or ""
    price = listing.get("price")
    rooms = listing.get("rooms")
    area  = listing.get("area")

    if soft.max_price and price:
        if price <= soft.max_price:
            parts.append(f"Price {price:,} CHF fits your budget of {soft.max_price:,} CHF")
        else:
            parts.append(f"Price {price:,} CHF slightly over budget ({soft.max_price:,} CHF)")

    if soft.min_rooms and rooms:
        if rooms >= soft.min_rooms:
            parts.append(f"{rooms} rooms matches your requirement of {soft.min_rooms}+")
        else:
            parts.append(f"{rooms} rooms (you asked for {soft.min_rooms}+)")

    if soft.min_area and area:
        if area >= soft.min_area:
            parts.append(f"{area:.0f} m² meets your minimum of {soft.min_area:.0f} m²")
        else:
            parts.append(f"{area:.0f} m² (below your target of {soft.min_area:.0f} m²)")

    if soft.city:
        city_val = listing.get("city") or ""
        if any(city_val.lower() == c.lower() for c in soft.city):
            parts.append(f"Located in {city_val} as requested")

    if soft.features:
        matched = [f for f in soft.features if listing.get(f"feature_{f}") == 1]
        missing = [f for f in soft.features if listing.get(f"feature_{f}") != 1]
        if matched:
            parts.append(f"Has requested features: {', '.join(matched)}")
        if missing:
            parts.append(f"Missing features: {', '.join(missing)}")

    if getattr(soft, "furnished", None):
        parts.append("Furnished as requested" if cat == "Möblierte Wohnung" else "Listed as unfurnished")

    if getattr(soft, "garden", None):
        parts.append("House type — likely has a garden" if cat in _HOUSE_CATEGORIES else "No private garden (apartment)")

    min_bed = getattr(soft, "min_bedrooms", None)
    if min_bed and rooms:
        est = max(0, int(rooms - 1))
        parts.append(f"~{est} estimated bedroom(s) (you asked for {min_bed}+)")

    if getattr(soft, "rooftop", None):
        has = (extracted.has_rooftop if extracted and extracted.has_rooftop is not None
               else cat in _ROOFTOP_CATEGORIES)
        parts.append("Rooftop / Dachterrasse access confirmed" if has else "No rooftop access indicated")

    if getattr(soft, "terrace", None):
        has = (extracted.has_terrace if extracted and extracted.has_terrace is not None
               else cat in _TERRACE_CATEGORIES)
        parts.append("Has terrace" if has else "No dedicated terrace indicated")

    # ── Description-extracted details ─────────────────────────────────────────
    if extracted:
        min_bath = getattr(soft, "min_bathrooms", None)
        if min_bath and extracted.bathrooms is not None:
            parts.append(f"{extracted.bathrooms} bathroom(s) found (you asked for {min_bath}+)")

        if getattr(soft, "cellar", None) and extracted.has_cellar is not None:
            parts.append("Cellar/storage confirmed" if extracted.has_cellar else "No cellar mentioned")

        if getattr(soft, "bathtub", None) and extracted.has_bathtub is not None:
            parts.append("Bathtub confirmed" if extracted.has_bathtub else "No bathtub mentioned")

        if getattr(soft, "view", None) and extracted.has_view is not None:
            parts.append("Notable view confirmed" if extracted.has_view else "No notable view mentioned")

    # ── Always-on facts ───────────────────────────────────────────────────────
    if price and area:
        parts.append(f"{round(price / area, 1)} CHF/m²")

    if not parts:
        parts.append(f"General match to your query ({q:.0%} similarity)")

    return ". ".join(parts) + "."


def _has_geo_target(target: HardFilters) -> bool:
    return bool(target.geo_targets) or (
        target.latitude is not None and target.longitude is not None
    )


def _nearest_target_distance(
    listing_lat: float,
    listing_lon: float,
    target: HardFilters,
) -> float | None:
    target_points = [
        (geo_target.latitude, geo_target.longitude)
        for geo_target in (target.geo_targets or [])
    ]
    if not target_points and target.latitude is not None and target.longitude is not None:
        target_points = [(target.latitude, target.longitude)]
    if not target_points:
        return None
    return min(
        _distance_km(target_lat, target_lon, listing_lat, listing_lon)
        for target_lat, target_lon in target_points
    )


def _to_listing_data(c: dict[str, Any]) -> ListingData:
    return ListingData(
        id=str(c["listing_id"]),
        title=c["title"],
        description=c.get("description"),
        street=c.get("street"),
        city=c.get("city"),
        postal_code=c.get("postal_code"),
        canton=c.get("canton"),
        latitude=c.get("latitude"),
        longitude=c.get("longitude"),
        price_chf=c.get("price"),
        rooms=c.get("rooms"),
        living_area_sqm=c.get("area"),
        available_from=c.get("available_from"),
        image_urls=_coerce_image_urls(c.get("image_urls")),
        hero_image_url=c.get("hero_image_url"),
        original_listing_url=c.get("original_url"),
        features=c.get("features") or [],
        offer_type=c.get("offer_type"),
        object_category=c.get("object_category"),
        object_type=c.get("object_type"),
        distance_public_transport=c.get("distance_public_transport"),
        distance_shop=c.get("distance_shop"),
    )


def _coerce_image_urls(value: Any) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, list):
        return [str(i) for i in value]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(i) for i in parsed]
        except json.JSONDecodeError:
            return [value]
    return None
