from __future__ import annotations

import json
from typing import Any

from app.core.hard_filters import _distance_km
from app.models.schemas import HardFilters, ListingData, RankedListingResult


_W_QUERY_GEO    = 0.4
_W_GEO          = 0.4
_W_SOFT_GEO     = 0.2

_W_QUERY_NO_GEO = 0.6
_W_SOFT_NO_GEO  = 0.4

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


def _score(listing: dict[str, Any], soft: HardFilters, hard: HardFilters, query_sim: float = 0.0) -> float:
    q = max(0.0, min(1.0, query_sim))
    geo = _geo_score(listing, soft, hard)
    soft_s = _soft_score(listing, soft)
    if geo > 0.0 or _has_geo_target(hard) or _has_geo_target(soft):
        return round(_W_QUERY_GEO * q + _W_GEO * geo + _W_SOFT_GEO * soft_s, 4)
    return round(_W_QUERY_NO_GEO * q + _W_SOFT_NO_GEO * soft_s, 4)


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


def _soft_score(listing: dict[str, Any], soft: HardFilters) -> float:
    """Average of per-criterion [0,1] scores for every soft preference that is set."""
    scores: list[float] = []

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
        scores.append(1.0 if listing.get("object_category") == "Möblierte Wohnung" else 0.0)

    if not scores:
        return 0.0
    return sum(scores) / len(scores)


def _reason(listing: dict[str, Any], soft: HardFilters, hard: HardFilters, query_sim: float = 0.0) -> str:
    parts = []

    q = max(0.0, min(1.0, query_sim))
    geo = _geo_score(listing, soft, hard)
    soft_s = _soft_score(listing, soft)

    parts.append(f"semantic {q:.0%}")
    parts.append(f"geo {geo:.0%}")
    parts.append(f"soft {soft_s:.0%}")

    lat = listing.get("latitude")
    lon = listing.get("longitude")
    if lat is not None and lon is not None and geo > 0.0:
        target = hard if _has_geo_target(hard) else soft
        dist_km = _nearest_target_distance(lat, lon, target)
        if dist_km is not None:
            parts.append(f"{dist_km:.1f} km")

    price = listing.get("price")
    area = listing.get("area")
    if price and area:
        parts.append(f"{round(price / area, 1)} CHF/m²")

    return "; ".join(parts)


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
