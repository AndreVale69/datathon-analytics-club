from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.db import get_connection


@dataclass(slots=True)
class HardFilterParams:
    city: list[str] | None = None
    postal_code: list[str] | None = None
    canton: str | None = None
    min_price: int | None = None
    max_price: int | None = None
    min_rooms: float | None = None
    max_rooms: float | None = None
    min_area: float | None = None
    max_area: float | None = None
    available_before: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    radius_km: float | None = None
    features: list[str] | None = None
    offer_type: str | None = None
    object_category: list[str] | None = None
    limit: int = 20
    offset: int = 0
    sort_by: str | None = None


FEATURE_COLUMN_MAP = {
    "balcony": "feature_balcony",
    "elevator": "feature_elevator",
    "parking": "feature_parking",
    "garage": "feature_garage",
    "fireplace": "feature_fireplace",
    "child_friendly": "feature_child_friendly",
    "pets_allowed": "feature_pets_allowed",
    "temporary": "feature_temporary",
    "new_build": "feature_new_build",
    "wheelchair_accessible": "feature_wheelchair_accessible",
    "private_laundry": "feature_private_laundry",
    "minergie_certified": "feature_minergie_certified",
}


def _normalize_umlauts(s: str) -> str:
    return s.replace("ü", "u").replace("ö", "o").replace("ä", "a").replace("é", "e").replace("è", "e")


def _normalize_list(values: list[str] | None) -> list[str] | None:
    if not values:
        return None
    cleaned = [value.strip() for value in values if value and value.strip()]
    return cleaned or None


def search_listings(db_path: Path, filters: HardFilterParams) -> list[dict[str, Any]]:
    where_clauses: list[str] = []
    params: list[Any] = []

    # ── Location ──────────────────────────────────────────────────────────────
    city = _normalize_list(filters.city)
    if city:
        placeholders = ", ".join("?" for _ in city)
        umlaut_sql = (
            "REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LOWER(city),"
            "'ü','u'),'ö','o'),'ä','a'),'é','e'),'è','e')"
        )
        where_clauses.append(f"{umlaut_sql} IN ({placeholders})")
        params.extend(_normalize_umlauts(v.lower()) for v in city)

    postal_code = _normalize_list(filters.postal_code)
    if postal_code:
        placeholders = ", ".join("?" for _ in postal_code)
        where_clauses.append(f"postal_code IN ({placeholders})")
        params.extend(postal_code)

    if filters.canton:
        where_clauses.append("UPPER(canton) = ?")
        params.append(filters.canton.upper())

    # ── Price ─────────────────────────────────────────────────────────────────
    if filters.min_price is not None:
        where_clauses.append("price >= ?")
        params.append(filters.min_price)

    if filters.max_price is not None:
        where_clauses.append("price <= ?")
        params.append(filters.max_price)

    # ── Size ──────────────────────────────────────────────────────────────────
    if filters.min_rooms is not None:
        where_clauses.append("rooms >= ?")
        params.append(filters.min_rooms)

    if filters.max_rooms is not None:
        where_clauses.append("rooms <= ?")
        params.append(filters.max_rooms)

    if filters.min_area is not None:
        where_clauses.append("area >= ?")
        params.append(filters.min_area)

    if filters.max_area is not None:
        where_clauses.append("area <= ?")
        params.append(filters.max_area)

    # ── Availability ──────────────────────────────────────────────────────────
    # Keep listings that are already available (NULL) OR become available by the date
    if filters.available_before is not None:
        where_clauses.append("(available_from IS NULL OR available_from <= ?)")
        params.append(filters.available_before)

    # ── Offer type & category ─────────────────────────────────────────────────
    if filters.offer_type:
        where_clauses.append("UPPER(offer_type) = ?")
        params.append(filters.offer_type.upper())

    object_category = _normalize_list(filters.object_category)
    if object_category:
        placeholders = ", ".join("?" for _ in object_category)
        where_clauses.append(f"object_category IN ({placeholders})")
        params.extend(object_category)

    # ── Boolean features (AND semantics) ──────────────────────────────────────
    features = _normalize_list(filters.features)
    if features:
        for feature_name in features:
            column_name = FEATURE_COLUMN_MAP.get(feature_name)
            if column_name:
                where_clauses.append(f"{column_name} = 1")

    # ── Build query ───────────────────────────────────────────────────────────
    query = """
        SELECT
            listing_id,
            title,
            description,
            street,
            city,
            postal_code,
            canton,
            price,
            rooms,
            area,
            available_from,
            latitude,
            longitude,
            distance_public_transport,
            distance_shop,
            distance_kindergarten,
            distance_school_1,
            distance_school_2,
            features_json,
            offer_type,
            object_category,
            object_type,
            original_url,
            images_json
        FROM listings
    """

    if where_clauses:
        query += " WHERE " + " AND ".join(where_clauses)

    query += " ORDER BY " + _sort_clause(filters.sort_by)

    with get_connection(db_path) as connection:
        rows = connection.execute(query, params).fetchall()

    parsed_rows = [_parse_row(dict(row)) for row in rows]

    # ── Geo radius filter (in-memory Haversine) ───────────────────────────────
    if (
        filters.latitude is not None
        and filters.longitude is not None
        and filters.radius_km is not None
    ):
        nearby: list[tuple[float, dict[str, Any]]] = []
        for row in parsed_rows:
            if row.get("latitude") is None or row.get("longitude") is None:
                continue
            dist = _distance_km(filters.latitude, filters.longitude, row["latitude"], row["longitude"])
            if dist <= filters.radius_km:
                nearby.append((dist, row))
        nearby.sort(key=lambda x: (x[0], x[1]["listing_id"]))
        parsed_rows = [row for _, row in nearby]

    return parsed_rows[filters.offset: filters.offset + filters.limit]


def _parse_row(row: dict[str, Any]) -> dict[str, Any]:
    features_json = row.pop("features_json", "[]")
    images_json = row.pop("images_json", None)
    try:
        row["features"] = json.loads(features_json) if features_json else []
    except json.JSONDecodeError:
        row["features"] = []
    row["image_urls"] = _extract_image_urls(images_json)
    row["hero_image_url"] = row["image_urls"][0] if row["image_urls"] else None
    return row


def _extract_image_urls(images_json: Any) -> list[str]:
    if not images_json:
        return []
    try:
        parsed = json.loads(images_json) if isinstance(images_json, str) else images_json
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, dict):
        return []
    image_urls: list[str] = []
    for item in parsed.get("images", []) or []:
        if isinstance(item, dict) and item.get("url"):
            image_urls.append(str(item["url"]))
        elif isinstance(item, str) and item:
            image_urls.append(item)
    for item in parsed.get("image_paths", []) or []:
        if isinstance(item, str) and item:
            image_urls.append(item)
    return image_urls


def _distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _sort_clause(sort_by: str | None) -> str:
    return {
        "price_asc":  "price ASC NULLS LAST, listing_id ASC",
        "price_desc": "price DESC NULLS LAST, listing_id ASC",
        "rooms_asc":  "rooms ASC NULLS LAST, listing_id ASC",
        "rooms_desc": "rooms DESC NULLS LAST, listing_id ASC",
        "area_asc":   "area ASC NULLS LAST, listing_id ASC",
        "area_desc":  "area DESC NULLS LAST, listing_id ASC",
    }.get(sort_by or "", "listing_id ASC")
