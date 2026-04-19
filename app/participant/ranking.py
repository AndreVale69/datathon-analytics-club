from __future__ import annotations

import json
from typing import Any

from app.core.hard_filters import _distance_km
from app.models.schemas import HardFilters, ListingData, RankedListingResult


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
) -> list[RankedListingResult]:
    sims = query_similarities or {}
    hard = hard or HardFilters()
    results = [
        RankedListingResult(
            listing_id=str(c["listing_id"]),
            score=_score(c, soft, hard, sims.get(str(c["listing_id"]), 0.0)),
            reason=_reason(c, soft, hard, sims.get(str(c["listing_id"]), 0.0)),
            listing=_to_listing_data(c),
        )
        for c in candidates
    ]
    return sorted(results, key=lambda x: x.score, reverse=True)


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


def _score(listing: dict[str, Any], soft: HardFilters, hard: HardFilters, query_sim: float = 0.0) -> float:
    w_query, w_geo, w_soft = _weights(soft, hard)
    q     = max(0.0, min(1.0, query_sim))
    geo   = _geo_score(listing, soft, hard)
    soft_s = _soft_score(listing, soft)
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


def _count_soft_constraints(soft: HardFilters) -> int:
    """Count scoreable soft criteria (mirrors _soft_score — only what we can verify)."""
    n = 0
    if soft.features:                           n += 1
    if soft.max_price:                          n += 1
    if soft.min_rooms:                          n += 1
    if soft.min_area:                           n += 1
    if soft.city:                               n += 1
    if getattr(soft, "furnished", None):        n += 1
    if getattr(soft, "garden", None):           n += 1
    if getattr(soft, "min_bedrooms", None):     n += 1
    if getattr(soft, "rooftop", None):          n += 1
    if getattr(soft, "terrace", None):          n += 1
    return n


def _soft_score(listing: dict[str, Any], soft: HardFilters) -> float:
    """Average of per-criterion [0,1] scores for every verifiable soft preference."""
    scores: list[float] = []
    cat = listing.get("object_category") or ""

    # Requested features
    if soft.features:
        matched = sum(1 for f in soft.features if listing.get(f"feature_{f}") == 1)
        scores.append(matched / len(soft.features))

    # Price fit
    price = listing.get("price")
    if soft.max_price and price:
        scores.append(max(0.0, min(1.0, 1.0 - price / soft.max_price)))

    # Rooms fit
    rooms = listing.get("rooms")
    if soft.min_rooms and rooms:
        scores.append(max(0.0, 1.0 - abs(rooms - soft.min_rooms) / soft.min_rooms))

    # Area fit
    area = listing.get("area")
    if soft.min_area and area:
        scores.append(max(0.0, 1.0 - abs(area - soft.min_area) / soft.min_area))

    # City match
    if soft.city:
        city = (listing.get("city") or "").lower()
        scores.append(1.0 if any(city == c.lower() for c in soft.city) else 0.0)

    # Furnished
    if getattr(soft, "furnished", None):
        scores.append(1.0 if cat == "Möblierte Wohnung" else 0.0)

    # Garden — proxy: house-type category
    if getattr(soft, "garden", None):
        scores.append(1.0 if cat in _HOUSE_CATEGORIES else 0.0)

    # Min bedrooms — approximated: bedrooms ≈ rooms − 1 (Swiss notation)
    min_bed = getattr(soft, "min_bedrooms", None)
    if min_bed and rooms:
        estimated_bedrooms = max(0.0, rooms - 1)
        scores.append(1.0 if estimated_bedrooms >= min_bed else
                      max(0.0, estimated_bedrooms / min_bed))

    # Rooftop access — Dachwohnung / Attika
    if getattr(soft, "rooftop", None):
        scores.append(1.0 if cat in _ROOFTOP_CATEGORIES else 0.0)

    # Terrace — Terrassenwohnung / Maisonette
    if getattr(soft, "terrace", None):
        scores.append(1.0 if cat in _TERRACE_CATEGORIES else 0.0)

    if not scores:
        return 0.0
    return sum(scores) / len(scores)


def _reason(listing: dict[str, Any], soft: HardFilters, hard: HardFilters, query_sim: float = 0.0) -> str:
    w_query, w_geo, w_soft = _weights(soft, hard)
    q      = max(0.0, min(1.0, query_sim))
    geo    = _geo_score(listing, soft, hard)
    soft_s = _soft_score(listing, soft)

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
        parts.append("Rooftop / Dachterrasse access" if cat in _ROOFTOP_CATEGORIES else "No rooftop access indicated")

    if getattr(soft, "terrace", None):
        parts.append("Has terrace" if cat in _TERRACE_CATEGORIES else "No dedicated terrace indicated")

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
