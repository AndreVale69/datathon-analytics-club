from __future__ import annotations

from dataclasses import dataclass
import re

from app.core.geocoding import geocode_place
from app.models.schemas import HardFilters

_WITHIN_RADIUS_RE = re.compile(
    r"\bwithin\s+(?P<radius>\d+(?:\.\d+)?)\s*km\s+of\s+(?P<place>.+)",
    re.IGNORECASE,
)
_NEAR_RE = re.compile(
    r"\b(?P<operator>near|close to|around)\s+(?P<place>.+)",
    re.IGNORECASE,
)
_PLACE_STOP_RE = re.compile(
    r"\b("
    r"with|under|below|over|above|max(?:imum)?|min(?:imum)?|budget|price|rent|"
    r"rooms?|bedrooms?|balcony|parking|garage|garden|bright|modern|quiet|"
    r"family(?:-friendly)?|student|available|from|starting|for"
    r")\b",
    re.IGNORECASE,
)

_DEFAULT_NEAR_RADIUS_KM = 3.0
_DEFAULT_AROUND_RADIUS_KM = 5.0


@dataclass(slots=True)
class PlaceConstraint:
    place: str
    radius_km: float


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

    place_constraint = _extract_place_constraint(query)
    if place_constraint is None:
        return hard_filters

    geocoded_place = geocode_place(place_constraint.place)
    if geocoded_place is None:
        return hard_filters

    hard_filters.latitude = geocoded_place.latitude
    hard_filters.longitude = geocoded_place.longitude
    if hard_filters.radius_km is None:
        hard_filters.radius_km = place_constraint.radius_km
    return hard_filters


def _extract_place_constraint(query: str) -> PlaceConstraint | None:
    explicit_radius_match = _WITHIN_RADIUS_RE.search(query)
    if explicit_radius_match:
        radius_km = float(explicit_radius_match.group("radius"))
        place = _clean_place_text(explicit_radius_match.group("place"))
        if place:
            return PlaceConstraint(place=place, radius_km=radius_km)

    nearby_match = _NEAR_RE.search(query)
    if nearby_match:
        operator = nearby_match.group("operator").lower()
        place = _clean_place_text(nearby_match.group("place"))
        if place:
            radius_km = (
                _DEFAULT_AROUND_RADIUS_KM if operator == "around" else _DEFAULT_NEAR_RADIUS_KM
            )
            return PlaceConstraint(place=place, radius_km=radius_km)

    return None


def _clean_place_text(value: str) -> str:
    trimmed = value.strip().strip(" ,.;:!?")
    delimiter_index = len(trimmed)
    for delimiter in (",", ";"):
        index = trimmed.find(delimiter)
        if index != -1:
            delimiter_index = min(delimiter_index, index)
    trimmed = trimmed[:delimiter_index].strip()

    stop_match = _PLACE_STOP_RE.search(trimmed)
    if stop_match:
        trimmed = trimmed[: stop_match.start()].strip()

    return trimmed.strip(" ,.;:!?")
