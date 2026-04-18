from __future__ import annotations

import math
import os

from pydantic import BaseModel, Field

from app.core.geocoding import GeocodedPlace, geocode_place
from app.models.schemas import HardFilters, QueryConstraints


_GEOLOCATION_SYSTEM_PROMPT = """\
You extract place-proximity intent for a Swiss real-estate search system.

Given a user query, decide whether it references a SPECIFIC NAMED PLACE that requires
geocoding (a landmark, university, station name, address, district, airport, campus…).

Return a JSON object with two keys: "hard" and "soft".
Each may contain:
  - places: list of objects with:
      - query: exact place text to send to the geocoding API
      - radius_km: explicit radius only when the user states one numerically

Rules:
  INCLUDE — specific named places:
    "near ETH Zurich"          → query="ETH Zurich"
    "close to Zurich HB"       → query="Zurich HB"
    "within 2km of Paradeplatz"→ query="Paradeplatz Zurich", radius_km=2
    "près de la gare de Sion"  → query="Gare de Sion"
    "nahe Universität Bern"    → query="Universität Bern"

  EXCLUDE — generic amenity types (handled by distance fields elsewhere):
    "near a school", "close to public transport", "near a shop", "near kindergarten"
    → these are NOT specific places, omit them entirely.

  EXCLUDE — any city or municipality name (handled as city filters elsewhere):
    "in Zurich", "near Zurich", "close to Bern", "proche de Genève",
    "Nähe Basel", "around Lausanne" → ALL omit — city names are not geocoded here.

  hard  : user clearly requires proximity ("must", "need", "max X km from").
  soft  : user expresses a preference ("ideally", "if possible", "would like to be near").

  If no specific named place is found, return {{"hard": {{}}, "soft": {{}}}}.
  If no explicit radius is given, omit radius_km (a default will be applied).
  Output only the JSON object, no explanation.\
"""


class GeocodingQuery(BaseModel):
    query: str
    radius_km: float | None = Field(default=None, ge=0)


class GeolocationIntent(BaseModel):
    places: list[GeocodingQuery] = Field(default_factory=list)


class GeolocationConstraints(BaseModel):
    hard: GeolocationIntent = Field(default_factory=GeolocationIntent)
    soft: GeolocationIntent = Field(default_factory=GeolocationIntent)


# Default radius when the user says "near" without a number
_DEFAULT_RADIUS_KM = 3.0


def extract_geolocation_constraints(query: str) -> GeolocationConstraints:
    try:
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_openai import ChatOpenAI

        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        llm = ChatOpenAI(model=model, temperature=0, seed=42).with_structured_output(
            GeolocationConstraints.model_json_schema()
        )
        prompt = ChatPromptTemplate.from_messages(
            [("system", _GEOLOCATION_SYSTEM_PROMPT), ("human", "{query}")]
        )
        raw = (prompt | llm).invoke({"query": query})
        return GeolocationConstraints(**raw)
    except Exception:
        return GeolocationConstraints()


def enrich_constraints_with_geolocation(
    query: str,
    constraints: QueryConstraints,
) -> QueryConstraints:
    enriched = constraints.model_copy(deep=True)
    geo = extract_geolocation_constraints(query)
    _apply_intent(enriched.hard, geo.hard)
    _apply_intent(enriched.soft, geo.soft)
    return enriched


def _apply_intent(filters: HardFilters, intent: GeolocationIntent) -> None:
    if not intent.places:
        return
    if filters.latitude is not None or filters.longitude is not None:
        return

    geocoded = [geocode_place(p.query) for p in intent.places]
    geocoded = [g for g in geocoded if g is not None]
    if not geocoded:
        return

    # Compute centroid of all matched places
    lat, lon = _centroid(geocoded)
    filters.latitude = lat
    filters.longitude = lon

    if filters.radius_km is None:
        # Use explicit radii from queries if provided, else default
        explicit = [p.radius_km for p in intent.places if p.radius_km is not None]
        base_radius = max(explicit) if explicit else _DEFAULT_RADIUS_KM

        # If multiple points, expand radius to cover spread between them
        if len(geocoded) > 1:
            spread = _max_distance_from_centroid(lat, lon, geocoded)
            filters.radius_km = round(base_radius + spread, 2)
        else:
            filters.radius_km = base_radius


def _centroid(points: list[GeocodedPlace]) -> tuple[float, float]:
    lat = sum(p.latitude for p in points) / len(points)
    lon = sum(p.longitude for p in points) / len(points)
    return round(lat, 6), round(lon, 6)


def _max_distance_from_centroid(
    clat: float, clon: float, points: list[GeocodedPlace]
) -> float:
    return max(_haversine_km(clat, clon, p.latitude, p.longitude) for p in points)


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(
        math.radians(lat2)
    ) * math.sin(dlon / 2) ** 2
    return r * 2 * math.asin(math.sqrt(a))
