from __future__ import annotations

import json
from typing import Any

from app.core.hard_filters import _distance_km
from app.models.schemas import HardFilters, ListingData, RankedListingResult


def rank_listings(
    candidates: list[dict[str, Any]],
    soft: HardFilters,
) -> list[RankedListingResult]:
    results = [
        RankedListingResult(
            listing_id=str(c["listing_id"]),
            score=_score(c, soft),
            reason=_reason(c, soft),
            listing=_to_listing_data(c),
        )
        for c in candidates
    ]
    return sorted(results, key=lambda x: x.score, reverse=True)


def _score(listing: dict[str, Any], soft: HardFilters) -> float:
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

    # ── Soft geolocation preference ───────────────────────────────────────────
    listing_lat = listing.get("latitude")
    listing_lon = listing.get("longitude")
    if (
        listing_lat is not None
        and listing_lon is not None
        and soft.latitude is not None
        and soft.longitude is not None
    ):
        dist_km = _distance_km(soft.latitude, soft.longitude, listing_lat, listing_lon)
        if soft.radius_km:
            score += max(0.0, 1.0 - dist_km / soft.radius_km) * 1.2
        else:
            score += max(0.0, 1.0 - dist_km / 15.0) * 0.8

    return round(score, 4)


def _reason(listing: dict[str, Any], soft: HardFilters) -> str:
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

    if (
        listing.get("latitude") is not None
        and listing.get("longitude") is not None
        and soft.latitude is not None
        and soft.longitude is not None
    ):
        dist_km = _distance_km(
            soft.latitude,
            soft.longitude,
            listing["latitude"],
            listing["longitude"],
        )
        parts.append(f"{dist_km:.1f} km from preferred location")
    return "; ".join(parts) if parts else "good candidate"


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