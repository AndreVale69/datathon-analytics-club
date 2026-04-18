from app.models.schemas import HardFilters, QueryConstraints
from app.participant.constraint_extractor import extract_constraints
from app.participant.ranking import rank_listings
from app.participant.soft_filtering import filter_soft_facts
from app.harness.search_service import to_hard_filter_params


def test_extract_constraints_returns_query_constraints() -> None:
    result = extract_constraints("3 room flat in zurich")

    assert isinstance(result, QueryConstraints)


def test_participant_modules_are_importable() -> None:
    candidates = [{"listing_id": "1", "title": "Example"}]

    soft = HardFilters()
    filtered = filter_soft_facts(candidates, soft)
    ranked = rank_listings(filtered, soft)

    assert isinstance(filtered, list)
    assert all(item["listing_id"] in {"1"} for item in filtered)
    assert isinstance(ranked, list)
    assert ranked
    assert all(item.listing_id for item in ranked)
    assert all(isinstance(item.score, float) for item in ranked)


def test_harness_service_converts_hard_filters_to_search_params() -> None:
    filters = HardFilters(city=["Zurich"], features=["balcony"], limit=5, offset=2)

    params = to_hard_filter_params(filters)

    assert params.city == ["Zurich"]
    assert params.features == ["balcony"]
    assert params.limit == 5
    assert params.offset == 2
