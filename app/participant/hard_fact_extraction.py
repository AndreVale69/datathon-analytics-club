from __future__ import annotations

from app.core.geocoding import geocode_place
from app.models.schemas import HardFilters
from app.participant.geolocation_extractor import extract_geolocation_intent


def extract_constraints(query: str) -> HardFilters:
    try:
        from app.participant.constraint_extractor import extract_constraints as extractor
        return extractor(query)
    except Exception:
        return HardFilters()


def extract_hard_facts(query: str) -> HardFilters:
    hard_filters = extract_constraints(query)

    if hard_filters.latitude is not None or hard_filters.longitude is not None:
        return hard_filters

    geolocation_intent = extract_geolocation_intent(query)
    geocoding_query = (geolocation_intent.geocoding_query or "").strip()
    if not geocoding_query:
        return hard_filters

    geocoded_place = geocode_place(geocoding_query)
    if geocoded_place is None:
        return hard_filters

    hard_filters.latitude = geocoded_place.latitude
    hard_filters.longitude = geocoded_place.longitude
    if hard_filters.radius_km is None:
        hard_filters.radius_km = geolocation_intent.radius_km
    return hard_filters
