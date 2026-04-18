from __future__ import annotations

import os

from pydantic import BaseModel, Field

from app.core.geocoding import geocode_place
from app.models.schemas import HardFilters, QueryConstraints


_GEOLOCATION_SYSTEM_PROMPT = """\
You extract only place-proximity intent for a Swiss real-estate search system.

Given a user query in any language, decide whether the query contains a place reference
that should be resolved through a geocoding API.

Return a JSON object with two keys: "hard" and "soft".
Each may contain:
- geocoding_query: the exact place text that should be sent to the geocoding API
- radius_km: a radius only when the query explicitly or strongly requires a geographic radius

Rules:
- Use "hard" when the user clearly requires proximity.
- Use "soft" when the user expresses a preference, e.g. "possibly", "ideally", "would like", "preferably".
- Do not use city names already handled as normal city filters unless the user is asking for proximity
  to a landmark, station, campus, airport, district, address, or named place.
- Extract geocoding_query for examples like:
  "near ETH Zurich", "close to Lausanne station", "within 2 km of Lugano center",
  "près de la gare", "vicino all'aeroporto", "nahe Universität Zürich"
- "possibly near the ETH" should be a soft place preference.
- If there is no place-proximity intent, return an empty object.
- If the query implies proximity but no numeric radius is given, leave radius_km unset.
- Output only structured data.
"""


class GeolocationIntent(BaseModel):
    geocoding_query: str | None = None
    radius_km: float | None = Field(default=None, ge=0)


class GeolocationConstraints(BaseModel):
    hard: GeolocationIntent = Field(default_factory=GeolocationIntent)
    soft: GeolocationIntent = Field(default_factory=GeolocationIntent)


def extract_geolocation_constraints(query: str) -> GeolocationConstraints:
    try:
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_openai import ChatOpenAI

        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        llm = ChatOpenAI(
            model=model,
            temperature=0,
            seed=42,
        ).with_structured_output(GeolocationConstraints.model_json_schema())

        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", _GEOLOCATION_SYSTEM_PROMPT),
                ("human", "{query}"),
            ]
        )

        chain = prompt | llm
        raw = chain.invoke({"query": query})
        return GeolocationConstraints(**raw)
    except Exception:
        return GeolocationConstraints()


def enrich_constraints_with_geolocation(
    query: str,
    constraints: QueryConstraints,
) -> QueryConstraints:
    enriched = constraints.model_copy(deep=True)
    geolocation = extract_geolocation_constraints(query)

    _apply_geocoded_intent(enriched.hard, geolocation.hard)
    _apply_geocoded_intent(enriched.soft, geolocation.soft)

    return enriched


def _apply_geocoded_intent(filters: HardFilters, intent: GeolocationIntent) -> None:
    if filters.latitude is not None or filters.longitude is not None:
        return

    geocoding_query = (intent.geocoding_query or "").strip()
    if not geocoding_query:
        return

    geocoded_place = geocode_place(geocoding_query)
    if geocoded_place is None:
        return

    filters.latitude = geocoded_place.latitude
    filters.longitude = geocoded_place.longitude
    if filters.radius_km is None:
        filters.radius_km = intent.radius_km
