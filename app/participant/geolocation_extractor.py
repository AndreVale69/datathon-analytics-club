from __future__ import annotations

import os

from pydantic import BaseModel, Field


_GEOLOCATION_SYSTEM_PROMPT = """\
You extract only geolocation search intent for a Swiss real-estate search system.

Given a user query in any language, decide whether the query contains a place reference
that should be resolved through a geocoding API.

Return:
- geocoding_query: the exact place text that should be sent to the geocoding API
- radius_km: a hard radius only when the query explicitly or strongly requires a geographic radius

Rules:
- Do not use city names already handled as normal city filters unless the user is asking for proximity
  to a landmark, station, campus, airport, district, address, or named place.
- Extract geocoding_query for examples like:
  "near ETH Zurich", "close to Lausanne station", "within 2 km of Lugano center",
  "près de la gare", "vicino all'aeroporto", "nahe Universität Zürich"
- If there is no place-proximity intent, return an empty object.
- If the query implies proximity but no numeric radius is given, leave radius_km unset.
- Output only structured data.
"""


class GeolocationIntent(BaseModel):
    geocoding_query: str | None = None
    radius_km: float | None = Field(default=None, ge=0)


def extract_geolocation_intent(query: str) -> GeolocationIntent:
    try:
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_openai import ChatOpenAI

        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        llm = ChatOpenAI(
            model=model,
            temperature=0,
            seed=42,
        ).with_structured_output(GeolocationIntent.model_json_schema())

        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", _GEOLOCATION_SYSTEM_PROMPT),
                ("human", "{query}"),
            ]
        )

        chain = prompt | llm
        raw = chain.invoke({"query": query})
        return GeolocationIntent(**raw)
    except Exception:
        return GeolocationIntent()
