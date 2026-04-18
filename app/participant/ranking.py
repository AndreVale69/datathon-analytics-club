from __future__ import annotations

import json
from typing import Any

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

    # ── Price proximity ───────────────────────────────────────────────────────
    price = listing.get("price")
    if price and soft.max_price:
        # Reward listings well under the soft price ceiling
        score += max(0.0, 1.0 - price / soft.max_price)
    elif price and 300 <= price <= 10000:
        # Generic reward for reasonable price
        score += max(0.0, (10000 - price) / 10000) * 0.3

    # ── Rooms proximity ───────────────────────────────────────────────────────
    rooms = listing.get("rooms")
    if rooms and soft.min_rooms:
        score += max(0.0, 1.0 - abs(rooms - soft.min_rooms) / soft.min_rooms) * 0.5

    # ── Area proximity ────────────────────────────────────────────────────────
    area = listing.get("area")
    if area and soft.min_area:
        score += max(0.0, 1.0 - abs(area - soft.min_area) / soft.min_area) * 0.3

    # ── City preference ───────────────────────────────────────────────────────
    if soft.city:
        city = (listing.get("city") or "").lower()
        if any(city == c.lower() for c in soft.city):
            score += 1.0

    # ── Feature preferences ───────────────────────────────────────────────────
    if soft.features:
        for feat in soft.features:
            col = f"feature_{feat}"
            if listing.get(col) == 1:
                score += 0.5

    # ── Transport proximity ───────────────────────────────────────────────────
    dist_pt = listing.get("distance_public_transport")
    if dist_pt is not None:
        score += max(0.0, (500 - dist_pt) / 500) * 0.4

    return round(score, 4)


def _reason(listing: dict[str, Any], soft: HardFilters) -> str:
    parts = []
    price = listing.get("price")
    if price and soft.max_price and price <= soft.max_price:
        parts.append(f"price {price} CHF within budget")
    if soft.features:
        matched = [f for f in soft.features if listing.get(f"feature_{f}") == 1]
        if matched:
            parts.append(f"has preferred features: {', '.join(matched)}")
    if soft.city:
        city = listing.get("city", "")
        if any(city.lower() == c.lower() for c in soft.city):
            parts.append(f"in preferred city {city}")
    return "; ".join(parts) if parts else "matched hard filters"


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
