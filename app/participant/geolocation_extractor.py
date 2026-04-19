from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from app.core.geocoding import GeocodedPlace, geocode_places
from app.models.schemas import GeoTarget, HardFilters, QueryConstraints
from app.participant.llm_client import build_json_prompt_extractor

logger = logging.getLogger(__name__)


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
    "near ETH"                 → query="ETH"
    "near ETH Zurich"          → query="ETH"
    "close to Zurich HB"       → query="Zurich HB"
    "within 2km of Paradeplatz"→ query="Paradeplatz Zurich", radius_km=2
    "près de la gare de Sion"  → query="Gare de Sion"
    "nahe Universität Bern"    → query="Universität Bern"

  Short-name disambiguation:
    In Swiss housing-search context, if the user says just "ETH", assume the
    ETH / Universität quarter in Zurich and use query="ETH"
    unless the query clearly names another institution.

  EXCLUDE — generic amenity types (handled by distance fields elsewhere):
    "near a school", "close to public transport", "near a shop", "near kindergarten"
    → these are NOT specific places, omit them entirely.

  EXCLUDE — any city or municipality name (handled as city filters elsewhere):
    "in Zurich", "near Zurich", "close to Bern", "proche de Genève",
    "Nähe Basel", "around Lausanne" → ALL omit — city names are not geocoded here.

  hard  : user clearly requires proximity ("must", "need", "max X km from").
  soft  : user expresses a preference ("ideally", "if possible", "would like to be near").

  Classification examples:
    "near ETH"                       → hard place query "ETH"
    "within 2 km from ETH"           → hard place query "ETH" with radius_km=2
    "possibly near ETH"              → soft place query "ETH"
    "ideally near ETH Zurich"        → soft place query "ETH"
    "if possible close to Zurich HB" → soft place query "Zurich HB"
    "must be near ETH"               → hard place query "ETH"

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
_extractor = None


def extract_geolocation_constraints(query: str) -> GeolocationConstraints:
    global _extractor
    try:
        if _extractor is None:
            _extractor = build_json_prompt_extractor(
                system_prompt=_GEOLOCATION_SYSTEM_PROMPT,
                schema=GeolocationConstraints.model_json_schema(),
            )
        raw = _extractor.invoke({"query": query})
        constraints = GeolocationConstraints(**raw)
        return constraints
    except Exception as exc:
        logger.warning("Geolocation extraction unavailable for query %r: %s", query, exc)
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

    geocoded: list[GeocodedPlace] = []
    for place in intent.places:
        geocoded.extend(geocode_places(place.query))
    if not geocoded:
        return

    filters.geo_targets = [
        GeoTarget(label=place.label, latitude=place.latitude, longitude=place.longitude)
        for place in geocoded
    ]
    # Keep the first point for backward-compatible UI/meta consumers.
    filters.latitude = geocoded[0].latitude
    filters.longitude = geocoded[0].longitude

    if filters.radius_km is None:
        # Use explicit radii from queries if provided, else default
        explicit = [p.radius_km for p in intent.places if p.radius_km is not None]
        base_radius = max(explicit) if explicit else _DEFAULT_RADIUS_KM
        filters.radius_km = base_radius
