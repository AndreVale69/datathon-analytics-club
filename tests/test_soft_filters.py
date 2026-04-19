from app.models.schemas import HardFilters, QueryConstraints
from app.participant.ranking import rank_listings
from app.participant.soft_filtering import filter_soft_facts


def test_filter_soft_facts_returns_candidate_subset() -> None:
    candidates = [{"listing_id": "1"}, {"listing_id": "2"}]

    filtered = filter_soft_facts(candidates, QueryConstraints.SoftFilters())

    assert isinstance(filtered, list)
    assert {item["listing_id"] for item in filtered} <= {"1", "2"}


def test_rank_listings_returns_ranked_shape() -> None:
    ranked = rank_listings(
        candidates=[
            {
                "listing_id": "abc",
                "title": "Example",
                "city": "Zurich",
                "price": 2500,
                "rooms": 3.0,
                "latitude": 47.37,
                "longitude": 8.54,
                "street": "Main 1",
                "postal_code": "8000",
                "canton": "ZH",
                "area": 75.0,
                "available_from": "2026-06-01",
                "image_urls": ["https://example.com/1.jpg"],
                "hero_image_url": "https://example.com/1.jpg",
                "original_url": "https://example.com/listing",
                "features": ["balcony", "elevator"],
                "offer_type": "RENT",
                "object_category": "Wohnung",
                "object_type": "Apartment",
            }
        ],
        soft=QueryConstraints.SoftFilters(),
    )

    assert len(ranked) == 1
    assert ranked[0].listing_id == "abc"
    assert isinstance(ranked[0].score, float)
    assert isinstance(ranked[0].reason, str)
    assert ranked[0].listing.id == "abc"
    assert ranked[0].listing.title == "Example"
    assert ranked[0].listing.city == "Zurich"
    assert ranked[0].listing.image_urls


def test_rank_listings_prefers_closer_listing_for_hard_location() -> None:
    candidates = [
        {
            "listing_id": "near",
            "title": "Near ETH",
            "price": 2400,
            "rooms": 3.0,
            "area": 80.0,
            "latitude": 47.3773,
            "longitude": 8.5274,
        },
        {
            "listing_id": "far",
            "title": "Farther from ETH",
            "price": 900,
            "rooms": 5.0,
            "area": 120.0,
            "feature_balcony": 1,
            "feature_elevator": 1,
            "feature_parking": 1,
            "distance_public_transport": 50,
            "latitude": 47.36,
            "longitude": 8.49,
        },
    ]

    ranked = rank_listings(
        candidates=candidates,
        soft=HardFilters(),
        hard=HardFilters(latitude=47.377213, longitude=8.527311, radius_km=3.0),
    )

    assert [item.listing_id for item in ranked] == ["near", "far"]


def test_rank_listings_uses_nearest_of_multiple_hard_targets() -> None:
    candidates = [
        {
            "listing_id": "bovisa-home",
            "title": "Near Bovisa",
            "price": 2000,
            "rooms": 3.0,
            "area": 80.0,
            "latitude": 45.5052,
            "longitude": 9.1591,
        },
        {
            "listing_id": "leonardo-home",
            "title": "Near Leonardo",
            "price": 1000,
            "rooms": 3.0,
            "area": 80.0,
            "latitude": 45.4781,
            "longitude": 9.2282,
        },
    ]

    ranked = rank_listings(
        candidates=candidates,
        soft=HardFilters(max_price=1500),
        hard=HardFilters(
            radius_km=2.0,
            geo_targets=[
                {"label": "Bovisa", "latitude": 45.505, "longitude": 9.159},
                {"label": "Leonardo", "latitude": 45.478, "longitude": 9.228},
            ],
        ),
    )

    assert [item.listing_id for item in ranked] == ["leonardo-home", "bovisa-home"]
