from __future__ import annotations

from dataclasses import dataclass
from html import unescape
import re

import httpx

from app.config import get_settings


_HTML_TAG_RE = re.compile(r"<[^>]+>")


@dataclass(slots=True)
class GeocodedPlace:
    label: str
    latitude: float
    longitude: float


def geocode_place(query: str) -> GeocodedPlace | None:
    cleaned_query = query.strip()
    if not cleaned_query:
        return None

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
        return None

    if not isinstance(payload, dict):
        return None

    results = payload.get("results")
    if not isinstance(results, list) or not results:
        return None

    first_result = results[0]
    if not isinstance(first_result, dict):
        return None

    attrs = first_result.get("attrs")
    if not isinstance(attrs, dict):
        return None

    latitude = _coerce_float(attrs.get("lat"))
    longitude = _coerce_float(attrs.get("lon"))
    if latitude is None or longitude is None:
        return None

    label = str(attrs.get("label") or attrs.get("detail") or cleaned_query)
    return GeocodedPlace(
        label=_strip_html(label),
        latitude=latitude,
        longitude=longitude,
    )


def _coerce_float(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _strip_html(value: str) -> str:
    return unescape(_HTML_TAG_RE.sub("", value)).strip()
