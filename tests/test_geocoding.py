from __future__ import annotations

import os
from pathlib import Path
import sqlite3

import httpx
from fastapi.testclient import TestClient

from app.core.geocoding import GeocodedPlace, geocode_place, geocode_places
from app.core.hard_filters import HardFilterParams, _distance_km, search_listings
from app.harness.csv_import import create_schema
from app.models.schemas import HardFilters, QueryConstraints
from app.participant.constraint_extractor import extract_constraints
from app.participant.geolocation_extractor import (
    GeocodingQuery,
    GeolocationConstraints,
    GeolocationIntent,
)
from app.participant.ranking import rank_listings


def build_test_database(tmp_path: Path) -> Path:
    db_path = tmp_path / "listings.db"
    with sqlite3.connect(db_path) as connection:
        create_schema(connection)
        connection.executemany(
            """
            INSERT INTO listings (
                listing_id, platform_id, scrape_source, title, description, street, city,
                postal_code, canton, price, rooms, area, available_from, latitude, longitude,
                distance_public_transport, distance_shop, distance_kindergarten, distance_school_1,
                distance_school_2, feature_balcony, feature_elevator, feature_parking,
                feature_garage, feature_fireplace, feature_child_friendly, feature_pets_allowed,
                feature_temporary, feature_new_build, feature_wheelchair_accessible,
                feature_private_laundry, feature_minergie_certified, features_json, offer_type,
                object_category, object_type, original_url, images_json, location_address_json,
                orig_data_json, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "seed-1", "seed-1", "TEST", "Seed Listing", "Near station", "Main 1",
                    "Winterthur", "8400", "ZH", 2200, 3.5, 75, None, 47.499, 8.724,
                    120, 250, 400, 500, 600, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                    "[]", "RENT", "Wohnung", "Apartment", None, '{"images":[]}', "{}", "{}", "{}",
                ),
                (
                    "nearby-1", "nearby-1", "TEST", "Nearby Listing", "Walkable", "Main 2",
                    "Winterthur", "8400", "ZH", 2400, 4.0, 90, None, 47.503, 8.728,
                    160, 260, 420, 520, 610, 0, 1, 1, 0, 0, 1, 0, 0, 0, 0, 0, 0,
                    '["child_friendly"]', "RENT", "Wohnung", "Apartment", None,
                    '{"images":[]}', "{}", "{}", "{}",
                ),
                (
                    "far-1", "far-1", "TEST", "Far Listing", "Outside radius", "Main 3",
                    "Geneva", "1200", "GE", 2600, 3.0, 70, None, 46.204, 6.143,
                    300, 300, 450, 550, 650, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                    "[]", "RENT", "Wohnung", "Apartment", None, '{"images":[]}', "{}", "{}", "{}",
                ),
            ],
        )
        connection.commit()
    return db_path


def test_geocode_place_parses_geoadmin_location_payload(monkeypatch) -> None:
    def fake_get(url: str, *, params: dict[str, object], timeout: float) -> httpx.Response:
        request = httpx.Request("GET", url, params=params)
        assert params["searchText"] == "Zurich HB"
        assert params["type"] == "locations"
        return httpx.Response(
            200,
            request=request,
            json={
                "results": [
                    {
                        "attrs": {
                            "label": "<i>Station</i> <b>Zurich HB</b>",
                            "lat": 47.378177,
                            "lon": 8.540192,
                        }
                    }
                ]
            },
        )

    monkeypatch.setattr("app.core.geocoding.httpx.get", fake_get)

    place = geocode_place("Zurich HB")

    assert place == GeocodedPlace(
        label="Station Zurich HB",
        latitude=47.378177,
        longitude=8.540192,
    )


def test_geocode_place_returns_different_coordinates_for_different_places(monkeypatch) -> None:
    responses = {
        "ETH": {
            "results": [
                {
                    "attrs": {
                        "label": "<b>ETH Zurich</b>",
                        "lat": 47.3763,
                        "lon": 8.5476,
                    }
                }
            ]
        },
        "Lausanne station": {
            "results": [
                {
                    "attrs": {
                        "label": "<b>Lausanne station</b>",
                        "lat": 46.5160,
                        "lon": 6.6290,
                    }
                }
            ]
        },
    }

    def fake_get(url: str, *, params: dict[str, object], timeout: float) -> httpx.Response:
        query = str(params["searchText"])
        request = httpx.Request("GET", url, params=params)
        return httpx.Response(200, request=request, json=responses[query])

    monkeypatch.setattr("app.core.geocoding.httpx.get", fake_get)

    eth = geocode_place("ETH Zurich")
    lausanne = geocode_place("Lausanne station")

    assert eth is not None
    assert lausanne is not None
    assert eth.label == "ETH Zurich"
    assert lausanne.label == "Lausanne station"
    assert (eth.latitude, eth.longitude) != (lausanne.latitude, lausanne.longitude)


def test_geocode_place_normalizes_eth_zurich_to_eth_quarter(monkeypatch) -> None:
    def fake_get(url: str, *, params: dict[str, object], timeout: float) -> httpx.Response:
        request = httpx.Request("GET", url, params=params)
        assert params["searchText"] == "ETH"
        return httpx.Response(
            200,
            request=request,
            json={
                "results": [
                    {
                        "attrs": {
                            "label": "Quartierteil ETH / Universität (ZH) - Zürich",
                            "lat": 47.373661041259766,
                            "lon": 8.548020362854004,
                        }
                    }
                ]
            },
        )

    monkeypatch.setattr("app.core.geocoding.httpx.get", fake_get)

    place = geocode_place("ETH Zurich")

    assert place == GeocodedPlace(
        label="Quartierteil ETH / Universität (ZH) - Zürich",
        latitude=47.373661041259766,
        longitude=8.548020362854004,
    )


def test_geocode_places_returns_all_results_for_single_query(monkeypatch) -> None:
    def fake_get(url: str, *, params: dict[str, object], timeout: float) -> httpx.Response:
        request = httpx.Request("GET", url, params=params)
        assert params["searchText"] == "Politecnico di Milano"
        return httpx.Response(
            200,
            request=request,
            json={
                "results": [
                    {
                        "attrs": {
                            "label": "Politecnico di Milano - Bovisa",
                            "lat": 45.505,
                            "lon": 9.159,
                        }
                    },
                    {
                        "attrs": {
                            "label": "Politecnico di Milano - Leonardo",
                            "lat": 45.478,
                            "lon": 9.228,
                        }
                    },
                ]
            },
        )

    monkeypatch.setattr("app.core.geocoding.httpx.get", fake_get)

    places = geocode_places("Politecnico di Milano")

    assert places == [
        GeocodedPlace(label="Politecnico di Milano - Bovisa", latitude=45.505, longitude=9.159),
        GeocodedPlace(label="Politecnico di Milano - Leonardo", latitude=45.478, longitude=9.228),
    ]


def test_extract_constraints_resolves_hard_place_to_coordinates(monkeypatch) -> None:
    def fake_extract_geolocation_constraints(query: str) -> GeolocationConstraints:
        assert query == "bright apartment near Zurich HB with balcony"
        return GeolocationConstraints(
            hard=GeolocationIntent(
                places=[GeocodingQuery(query="Zurich HB", radius_km=3.0)]
            ),
            soft=GeolocationIntent(),
        )

    def fake_geocode(place: str) -> list[GeocodedPlace]:
        assert place == "Zurich HB"
        return [GeocodedPlace(label=place, latitude=47.378177, longitude=8.540192)]

    monkeypatch.setattr(
        "app.participant.constraint_extractor.extractor._extractor",
        type("StubExtractor", (), {"invoke": staticmethod(lambda payload: {"hard": {}, "soft": {}})})(),
    )
    monkeypatch.setattr(
        "app.participant.geolocation_extractor.extract_geolocation_constraints",
        fake_extract_geolocation_constraints,
    )
    monkeypatch.setattr("app.participant.geolocation_extractor.geocode_places", fake_geocode)

    constraints = extract_constraints("bright apartment near Zurich HB with balcony")

    assert constraints.hard.latitude == 47.378177
    assert constraints.hard.longitude == 8.540192
    assert constraints.hard.radius_km == 3.0


def test_enrich_constraints_with_geolocation_preserves_explicit_radius(monkeypatch) -> None:
    seen: list[str] = []

    def fake_geocode(place: str) -> list[GeocodedPlace]:
        seen.append(place)
        return [GeocodedPlace(label=place, latitude=46.5197, longitude=6.6323)]

    monkeypatch.setattr(
        "app.participant.geolocation_extractor.extract_geolocation_constraints",
        lambda query: GeolocationConstraints(
            hard=GeolocationIntent(
                places=[GeocodingQuery(query="Lausanne station", radius_km=1.5)]
            ),
            soft=GeolocationIntent(),
        ),
    )
    monkeypatch.setattr(
        "app.participant.geolocation_extractor.geocode_places",
        fake_geocode,
    )

    from app.participant.geolocation_extractor import enrich_constraints_with_geolocation

    constraints = enrich_constraints_with_geolocation(
        "studio within 1.5 km of Lausanne station under 2500 CHF",
        QueryConstraints(),
    )

    assert seen == ["Lausanne station"]
    assert constraints.hard.latitude == 46.5197
    assert constraints.hard.longitude == 6.6323
    assert constraints.hard.radius_km == 1.5


def test_query_endpoint_filters_results_around_geocoded_place(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_path = build_test_database(tmp_path)
    seed_rows = search_listings(db_path, HardFilterParams(city=["Winterthur"], limit=50))
    seed = next(
        row
        for row in seed_rows
        if row.get("latitude") is not None and row.get("longitude") is not None
    )

    def fake_geocode(place: str) -> list[GeocodedPlace]:
        assert place == "Winterthur station"
        return [
            GeocodedPlace(
                label=place,
                latitude=float(seed["latitude"]),
                longitude=float(seed["longitude"]),
            )
        ]

    monkeypatch.setattr(
        "app.participant.constraint_extractor.extractor._extractor",
        type("StubExtractor", (), {"invoke": staticmethod(lambda payload: {"hard": {}, "soft": {}})})(),
    )
    monkeypatch.setattr(
        "app.participant.geolocation_extractor.extract_geolocation_constraints",
        lambda query: GeolocationConstraints(
            hard=GeolocationIntent(
                places=[GeocodingQuery(query="Winterthur station", radius_km=3.0)]
            ),
            soft=GeolocationIntent(),
        ),
    )
    monkeypatch.setattr("app.participant.geolocation_extractor.geocode_places", fake_geocode)

    os.environ["LISTINGS_RAW_DATA_DIR"] = str(tmp_path)
    os.environ["LISTINGS_DB_PATH"] = str(db_path)

    from app.main import app

    with TestClient(app) as client:
        response = client.post("/listings", json={"query": "apartment near Winterthur station"})

    assert response.status_code == 200
    body = response.json()
    assert body["listings"]
    for item in body["listings"]:
        listing = item["listing"]
        assert listing["latitude"] is not None
        assert listing["longitude"] is not None
        assert (
            _distance_km(
                seed["latitude"],
                seed["longitude"],
                listing["latitude"],
                listing["longitude"],
            )
            <= 3.0
        )


def test_rank_listings_prefers_soft_geocoded_location() -> None:
    candidates = [
        {
            "listing_id": "near",
            "title": "Near ETH",
            "price": 2400,
            "rooms": 3.0,
            "area": 70,
            "latitude": 47.3763,
            "longitude": 8.5476,
            "features": [],
        },
        {
            "listing_id": "far",
            "title": "Far from ETH",
            "price": 2400,
            "rooms": 3.0,
            "area": 70,
            "latitude": 46.2044,
            "longitude": 6.1432,
            "features": [],
        },
    ]

    soft = HardFilters(latitude=47.3763, longitude=8.5476)
    ranked = rank_listings(candidates, soft)

    assert [item.listing_id for item in ranked] == ["near", "far"]


def test_enrich_constraints_with_geolocation_resolves_near_eth(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.participant.geolocation_extractor.extract_geolocation_constraints",
        lambda query: GeolocationConstraints(
            hard=GeolocationIntent(),
            soft=GeolocationIntent(places=[GeocodingQuery(query="ETH")]),
        ),
    )
    monkeypatch.setattr(
        "app.participant.geolocation_extractor.geocode_places",
        lambda place: [GeocodedPlace(label=place, latitude=47.3763, longitude=8.5476)],
    )

    from app.participant.geolocation_extractor import enrich_constraints_with_geolocation

    constraints = enrich_constraints_with_geolocation(
        "possibly near ETH",
        QueryConstraints(),
    )

    assert constraints.soft.latitude == 47.3763
    assert constraints.soft.longitude == 8.5476
    assert constraints.soft.radius_km == 3.0
    assert constraints.hard.latitude is None


def test_enrich_constraints_with_geolocation_resolves_within_2km_from_eth(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.participant.geolocation_extractor.extract_geolocation_constraints",
        lambda query: GeolocationConstraints(
            hard=GeolocationIntent(
                places=[GeocodingQuery(query="ETH", radius_km=2.0)]
            ),
            soft=GeolocationIntent(),
        ),
    )
    monkeypatch.setattr(
        "app.participant.geolocation_extractor.geocode_places",
        lambda place: [GeocodedPlace(label=place, latitude=47.3763, longitude=8.5476)],
    )

    from app.participant.geolocation_extractor import enrich_constraints_with_geolocation

    constraints = enrich_constraints_with_geolocation(
        "within 2 km from ETH",
        QueryConstraints(),
    )

    assert constraints.hard.latitude == 47.3763
    assert constraints.hard.longitude == 8.5476
    assert constraints.hard.radius_km == 2.0


def test_enrich_constraints_with_geolocation_keeps_all_targets(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.participant.geolocation_extractor.extract_geolocation_constraints",
        lambda query: GeolocationConstraints(
            hard=GeolocationIntent(places=[GeocodingQuery(query="Politecnico di Milano", radius_km=2.0)]),
            soft=GeolocationIntent(),
        ),
    )
    monkeypatch.setattr(
        "app.participant.geolocation_extractor.geocode_places",
        lambda place: [
            GeocodedPlace(label="Bovisa", latitude=45.505, longitude=9.159),
            GeocodedPlace(label="Leonardo", latitude=45.478, longitude=9.228),
        ],
    )

    from app.participant.geolocation_extractor import enrich_constraints_with_geolocation

    constraints = enrich_constraints_with_geolocation(
        "must be near Politecnico di Milano within 2 km",
        QueryConstraints(),
    )

    assert constraints.hard.radius_km == 2.0
    assert constraints.hard.geo_targets is not None
    assert len(constraints.hard.geo_targets) == 2
    assert {target.label for target in constraints.hard.geo_targets} == {"Bovisa", "Leonardo"}
