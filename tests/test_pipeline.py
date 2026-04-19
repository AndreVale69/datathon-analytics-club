from app.models.schemas import HardFilters, QueryConstraints
from app.participant.constraint_extractor import extract_constraints
from app.participant.geolocation_extractor import GeolocationConstraints
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


def test_extract_constraints_drops_unknown_feature_labels(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.participant.constraint_extractor.extractor._hard_extractor",
        type(
            "HardStubExtractor",
            (),
            {
                "invoke": staticmethod(
                    lambda payload: {"features": ["near_eth", "balcony"]}
                )
            },
        )(),
    )
    monkeypatch.setattr(
        "app.participant.constraint_extractor.extractor._soft_extractor",
        type("SoftStubExtractor", (), {"invoke": staticmethod(lambda payload: {})})(),
    )
    monkeypatch.setattr(
        "app.participant.geolocation_extractor.extract_geolocation_constraints",
        lambda query: GeolocationConstraints(),
    )

    result = extract_constraints("Apartments near ETH")

    assert result.hard.features == ["balcony"]


def test_extract_constraints_merges_hard_and_soft_layers(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.participant.constraint_extractor.extractor._hard_extractor",
        type(
            "HardStubExtractor",
            (),
            {
                "invoke": staticmethod(
                    lambda payload: {
                        "object_category": ["Wohnung"],
                        "city": ["Zurich", "Zürich"],
                        "min_price": 3000,
                        "max_price": 2000,
                    }
                )
            },
        )(),
    )
    monkeypatch.setattr(
        "app.participant.constraint_extractor.extractor._soft_extractor",
        type(
            "SoftStubExtractor",
            (),
            {"invoke": staticmethod(lambda payload: {"features": ["balcony"], "city": ["Zurich", "Zürich"]})},
        )(),
    )
    monkeypatch.setattr(
        "app.participant.geolocation_extractor.extract_geolocation_constraints",
        lambda query: GeolocationConstraints(),
    )

    result = extract_constraints("apartment in zurich under 3000 with balcony")

    assert result.hard.object_category == ["Wohnung"]
    assert result.hard.city == ["Zurich", "Zürich"]
    assert result.hard.min_price == 2000
    assert result.hard.max_price == 3000
    assert result.soft.features == ["balcony"]
    assert result.soft.city is None
