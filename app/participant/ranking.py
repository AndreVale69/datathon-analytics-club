from __future__ import annotations

import json
from typing import Any

from app.core.hard_filters import _distance_km
from app.models.schemas import HardFilters, ListingData, RankedListingResult


def rank_listings(
    candidates: list[dict[str, Any]],
    soft: HardFilters,
    hard: HardFilters | None = None,
) -> list[RankedListingResult]:
    hard_filters = hard or HardFilters()
    results = [
        RankedListingResult(
            listing_id=str(c["listing_id"]),
            score=_score(c, soft, hard_filters),
            reason=_reason(c, soft, hard_filters),
            listing=_to_listing_data(c),
        )
        for c in candidates
    ]
    return sorted(
        results,
        key=lambda item: _sort_key(item, hard_filters),
        reverse=True,
    )


def _score(listing: dict[str, Any], soft: HardFilters, hard: HardFilters) -> float:
    score = 0.0

    price = listing.get("price")
    rooms = listing.get("rooms")
    area = listing.get("area")

    # ── PRICE  ────────────────────────────────────────────────────
    if price:
        # se abbiamo budget utente → usalo
        if soft.max_price:
            score += max(0.0, 1.0 - price / soft.max_price)

        # fallback: premia prezzi realistici
        elif 300 <= price <= 10000:
            score += max(0.0, (10000 - price) / 10000) * 0.3

    # ── PRICE PER M2  ───────────────────────────────────────────────
    if price and area:
        price_per_m2 = price / area

        # range realistico svizzera ~15–30
        if price_per_m2 < 20:
            score += 1.0
        elif price_per_m2 < 30:
            score += 0.5

    # ── ROOMS ────────────────────────────────────────────────────────────────
    if rooms:
        if soft.min_rooms:
            score += max(0.0, 1.0 - abs(rooms - soft.min_rooms) / soft.min_rooms) * 0.5
        else:
            score += min(rooms / 5, 1.0)

    # ── AREA ─────────────────────────────────────────────────────────────────
    if area:
        if soft.min_area:
            score += max(0.0, 1.0 - abs(area - soft.min_area) / soft.min_area) * 0.3
        else:
            score += min(area / 100, 1.0)

    # ── CITY MATCH ───────────────────────────────────────────────────────────
    if soft.city:
        city = (listing.get("city") or "").lower()
        if any(city == c.lower() for c in soft.city):
            score += 1.5  # boost aumentato

    # ── FEATURES ─────────────────────────────────────────────────────────────
    if soft.features:
        for feat in soft.features:
            col = f"feature_{feat}"
            if listing.get(col) == 1:
                score += 0.5

    # ── FEATURE BONUS GENERALI (NUOVO) ────────────────────────────────────────
    if listing.get("feature_balcony") == 1:
        score += 0.3

    if listing.get("feature_elevator") == 1:
        score += 0.2

    if listing.get("feature_parking") == 1:
        score += 0.2

    # ── TRANSPORT ────────────────────────────────────────────────────────────
    dist_pt = listing.get("distance_public_transport")
    if dist_pt is not None:
        score += max(0.0, (500 - dist_pt) / 500) * 0.4

    # ── Geolocation preference and hard-radius closeness ─────────────────────
    listing_lat = listing.get("latitude")
    listing_lon = listing.get("longitude")
    if listing_lat is not None and listing_lon is not None:
        score += _location_score(listing_lat, listing_lon, hard, weight=5.0, strict=True)
        score += _location_score(listing_lat, listing_lon, soft, weight=4.0, strict=False)

    return round(score, 4)


def _sort_key(result: RankedListingResult, hard: HardFilters) -> tuple[float, float]:
    """
    Hard location queries should primarily rank by proximity to the required point.
    Score remains the tiebreaker within the same distance band.
    """
    if result.listing.latitude is not None and result.listing.longitude is not None:
        distance = _nearest_target_distance(
            result.listing.latitude,
            result.listing.longitude,
            hard,
        )
        if distance is not None:
            return -distance, result.score

    return result.score, 0.0


def _reason(listing: dict[str, Any], soft: HardFilters, hard: HardFilters) -> str:
    parts = []

    price = listing.get("price")
    area = listing.get("area")

    if price and soft.max_price and price <= soft.max_price:
        parts.append(f"price {price} CHF within budget")

    if price and area:
        ppm2 = round(price / area, 1)
        parts.append(f"{ppm2} CHF/m²")

    if soft.features:
        matched = [f for f in soft.features if listing.get(f"feature_{f}") == 1]
        if matched:
            parts.append(f"has features: {', '.join(matched)}")

    if soft.city:
        city = listing.get("city", "")
        if any(city.lower() == c.lower() for c in soft.city):
            parts.append(f"in {city}")

    listing_lat = listing.get("latitude")
    listing_lon = listing.get("longitude")
    if listing_lat is not None and listing_lon is not None:
        if _has_geo_target(hard):
            dist_km = _nearest_target_distance(listing_lat, listing_lon, hard)
            assert dist_km is not None
            parts.append(f"{dist_km:.1f} km from required location")
        elif _has_geo_target(soft):
            dist_km = _nearest_target_distance(listing_lat, listing_lon, soft)
            assert dist_km is not None
            parts.append(f"{dist_km:.1f} km from preferred location")
    return "; ".join(parts) if parts else "good candidate"


def _location_score(
    listing_lat: float,
    listing_lon: float,
    target: HardFilters,
    *,
    weight: float,
    strict: bool,
) -> float:
    dist_km = _nearest_target_distance(listing_lat, listing_lon, target)
    if dist_km is None:
        return 0.0
    preferred_radius_km = target.radius_km or 3.0
    effective_radius_km = min(preferred_radius_km, 4.0)

    if dist_km <= effective_radius_km:
        closeness = max(0.0, 1.0 - (dist_km / effective_radius_km))
        if strict:
            return weight + (closeness**2) * weight
        return (weight * 0.5) + (closeness**2) * weight

    overflow = dist_km - effective_radius_km
    penalty_span = max(preferred_radius_km, effective_radius_km)
    penalty = min(weight if strict else weight * 0.75, 1.0 + overflow / penalty_span)
    return -penalty


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
