from __future__ import annotations

import json
from typing import Any

from app.models.schemas import ListingData, RankedListingResult

def compute_score(listing, soft_facts):
    score = 0

    price = listing.get("price")
    rooms = listing.get("rooms")

    if price is None or price < 300 or price > 10000:
        return 0
    if rooms is None or rooms < 1 or rooms > 10:
        return 0

    score += max(0, 3000 - price) / 3000

    score += min(rooms, 5) / 5

    dist = listing.get("distance_public_transport")
    if dist is not None:
        score += max(0, 300 - dist) / 300

    if listing.get("feature_balcony") == 1:
        score += 1
    if listing.get("feature_parking") == 1:
        score += 0.5

    desc = (listing.get("description") or "").lower()
    for keyword in soft_facts.get("keywords", []):
        if keyword in desc:
            score += 2

    return score

def rank_listings(
    candidates: list[dict[str, Any]],
    soft_facts: dict[str, Any],
) -> list[RankedListingResult]:
    # Intentionally stubbed. Teams can replace this with a scoring or
    # reranking stage that uses the soft_facts payload.
    results = []

    for candidate in candidates:
        score = compute_score(candidate, soft_facts)

        results.append(
            RankedListingResult(
                listing_id=str(candidate["listing_id"]),
                score=score,
                reason=f"Score={score:.2f}",
                listing=_to_listing_data(candidate),
            )
        )

    return sorted(results, key=lambda x: x.score, reverse=True)


def _to_listing_data(candidate: dict[str, Any]) -> ListingData:
    return ListingData(
        id=str(candidate["listing_id"]),
        title=candidate["title"],
        description=candidate.get("description"),
        street=candidate.get("street"),
        city=candidate.get("city"),
        postal_code=candidate.get("postal_code"),
        canton=candidate.get("canton"),
        latitude=candidate.get("latitude"),
        longitude=candidate.get("longitude"),
        price_chf=candidate.get("price"),
        rooms=candidate.get("rooms"),
        living_area_sqm=_coerce_int(candidate.get("area")),
        available_from=candidate.get("available_from"),
        image_urls=_coerce_image_urls(candidate.get("image_urls")),
        hero_image_url=candidate.get("hero_image_url"),
        original_listing_url=candidate.get("original_url"),
        features=candidate.get("features") or [],
        offer_type=candidate.get("offer_type"),
        object_category=candidate.get("object_category"),
        object_type=candidate.get("object_type"),
    )


def _coerce_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None


def _coerce_image_urls(value: Any) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return [value]
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
    return None
