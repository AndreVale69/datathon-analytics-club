from __future__ import annotations

from dataclasses import dataclass
from html import unescape
import re

import httpx

from app.config import get_settings


_HTML_TAG_RE = re.compile(r"<[^>]+>")
_ETH_QUERY_RE = re.compile(r"^\s*eth(?:\s+zurich|\s+zürich)?\s*$", re.IGNORECASE)


@dataclass(slots=True)
class GeocodedPlace:
    label: str
    latitude: float
    longitude: float


def geocode_places(query: str) -> list[GeocodedPlace]:
    cleaned_query = _normalize_query(query)
    if not cleaned_query:
        return []

    settings = get_settings()

    try:
        response = httpx.get(
            settings.geocoding_api_base_url,
            params={
                "searchText": cleaned_query,
                "type": "locations",
                "limit": 1,
                "origins": "address,zipcode,gg25,gazetteer",
                "sr": 4326,
            },
            timeout=settings.geocoding_timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError):
        return []

    if not isinstance(payload, dict):
        return []

    results = payload.get("results")
    if not isinstance(results, list) or not results:
        return []

    places: list[GeocodedPlace] = []
    seen: set[tuple[float, float]] = set()
    for result in results:
        if not isinstance(result, dict):
            continue
        attrs = result.get("attrs")
        if not isinstance(attrs, dict):
            continue
        latitude = _coerce_float(attrs.get("lat"))
        longitude = _coerce_float(attrs.get("lon"))
        if latitude is None or longitude is None:
            continue
        key = (latitude, longitude)
        if key in seen:
            continue
        seen.add(key)
        label = str(attrs.get("label") or attrs.get("detail") or cleaned_query)
        places.append(
            GeocodedPlace(
                label=_strip_html(label),
                latitude=latitude,
                longitude=longitude,
            )
        )
    return places


def geocode_place(query: str) -> GeocodedPlace | None:
    places = geocode_places(query)
    return places[0] if places else None


def _coerce_float(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _strip_html(value: str) -> str:
    return unescape(_HTML_TAG_RE.sub("", value)).strip()


def _normalize_query(value: str) -> str:
    cleaned = value.strip()
    if _ETH_QUERY_RE.fullmatch(cleaned):
        return "ETH"
    return cleaned
