from __future__ import annotations

import os
from pathlib import Path
import sqlite3

import httpx
from fastapi.testclient import TestClient

from app.core.geocoding import GeocodedPlace, geocode_place
from app.core.hard_filters import HardFilterParams, _distance_km, search_listings
from app.harness.csv_import import create_schema
from app.participant.hard_fact_extraction import extract_hard_facts


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


def test_extract_hard_facts_resolves_near_place_to_coordinates(monkeypatch) -> None:
    def fake_extract_constraints(query: str):
        assert query == "bright apartment near Zurich HB with balcony"
        return HardFilters()

    def fake_geocode(place: str) -> GeocodedPlace | None:
        assert place == "Zurich HB"
        return GeocodedPlace(label=place, latitude=47.378177, longitude=8.540192)

    from app.models.schemas import HardFilters

    monkeypatch.setattr(
        "app.participant.hard_fact_extraction.extract_constraints",
        fake_extract_constraints,
    )
    monkeypatch.setattr("app.participant.hard_fact_extraction.geocode_place", fake_geocode)

    hard_filters = extract_hard_facts("bright apartment near Zurich HB with balcony")

    assert hard_filters.latitude == 47.378177
    assert hard_filters.longitude == 8.540192
    assert hard_filters.radius_km == 3.0


def test_extract_hard_facts_preserves_explicit_radius(monkeypatch) -> None:
    from app.models.schemas import HardFilters

    seen: list[str] = []

    def fake_extract_constraints(query: str) -> HardFilters:
        assert query == "studio within 1.5 km of Lausanne station under 2500 CHF"
        return HardFilters()

    def fake_geocode(place: str) -> GeocodedPlace | None:
        seen.append(place)
        return GeocodedPlace(label=place, latitude=46.5197, longitude=6.6323)

    monkeypatch.setattr(
        "app.participant.hard_fact_extraction.extract_constraints",
        fake_extract_constraints,
    )
    monkeypatch.setattr("app.participant.hard_fact_extraction.geocode_place", fake_geocode)

    hard_filters = extract_hard_facts("studio within 1.5 km of Lausanne station under 2500 CHF")

    assert seen == ["Lausanne station"]
    assert hard_filters.latitude == 46.5197
    assert hard_filters.longitude == 6.6323
    assert hard_filters.radius_km == 1.5


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

    def fake_geocode(place: str) -> GeocodedPlace | None:
        assert place == "Winterthur station"
        return GeocodedPlace(
            label=place,
            latitude=float(seed["latitude"]),
            longitude=float(seed["longitude"]),
        )

    from app.models.schemas import HardFilters

    monkeypatch.setattr(
        "app.participant.hard_fact_extraction.extract_constraints",
        lambda query: HardFilters(),
    )
    monkeypatch.setattr("app.participant.hard_fact_extraction.geocode_place", fake_geocode)

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
