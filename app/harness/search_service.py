from __future__ import annotations

from pathlib import Path
from typing import Any

from app.core.hard_filters import HardFilterParams, search_listings
from app.models.schemas import HardFilters, ListingsResponse, QueryConstraints
from app.participant.constraint_extractor import extract_constraints
from app.participant.ranking import rank_listings
from app.participant.soft_filtering import filter_soft_facts
from app.participant.description_analysis import compute_query_similarities
from app.participant.description_extractor import extract_features_from_descriptions


def query_from_text(
    *,
    db_path: Path,
    query: str,
    limit: int,
    offset: int,
) -> ListingsResponse:
    constraints = extract_constraints(query)

    constraints.hard.limit = limit
    constraints.hard.offset = offset

    candidates = search_listings(db_path, to_hard_filter_params(constraints.hard))

    query_similarities = compute_query_similarities(query, candidates)
    extracted_features = extract_features_from_descriptions(candidates, query_similarities)

    return ListingsResponse(
        listings=rank_listings(candidates, constraints.soft, constraints.hard, query_similarities, extracted_features),
        meta={
            "hard": constraints.hard.model_dump(exclude_none=True, exclude_defaults=True),
            "soft": constraints.soft.model_dump(exclude_none=True, exclude_defaults=True),
        },
    )


def query_from_filters(
    *,
    db_path: Path,
    hard_facts: HardFilters | None,
) -> ListingsResponse:
    hard = hard_facts or HardFilters()
    soft = QueryConstraints.SoftFilters()
    candidates = search_listings(db_path, to_hard_filter_params(hard))
    candidates = filter_soft_facts(candidates, soft)
    return ListingsResponse(
        listings=rank_listings(candidates, soft, hard),
        meta={
            "hard": hard.model_dump(exclude_none=True, exclude_defaults=True),
            "soft": soft.model_dump(exclude_none=True, exclude_defaults=True),
        },
    )


def to_hard_filter_params(hard_facts: HardFilters) -> HardFilterParams:
    return HardFilterParams(
        city=hard_facts.city,
        postal_code=hard_facts.postal_code,
        canton=hard_facts.canton,
        min_price=hard_facts.min_price,
        max_price=hard_facts.max_price,
        min_rooms=hard_facts.min_rooms,
        max_rooms=hard_facts.max_rooms,
        min_area=hard_facts.min_area,
        max_area=hard_facts.max_area,
        available_before=hard_facts.available_before,
        latitude=hard_facts.latitude,
        longitude=hard_facts.longitude,
        radius_km=hard_facts.radius_km,
        geo_targets=[
            (target.latitude, target.longitude) for target in (hard_facts.geo_targets or [])
        ] or None,
        features=hard_facts.features,
        offer_type=hard_facts.offer_type,
        object_category=hard_facts.object_category,
        limit=hard_facts.limit,
        offset=hard_facts.offset,
        sort_by=hard_facts.sort_by,
    )
