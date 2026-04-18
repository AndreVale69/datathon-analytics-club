from __future__ import annotations

import copy
import logging
import os

from project_env import load_project_env
from app.models.schemas import HardFilters, QueryConstraints
from app.participant.geolocation_extractor import enrich_constraints_with_geolocation

load_project_env()

logger = logging.getLogger(__name__)

_PAGINATION_FIELDS = {"limit", "offset", "sort_by"}


def _filters_schema() -> dict:
    """HardFilters JSON schema with pagination fields removed."""
    schema = copy.deepcopy(HardFilters.model_json_schema())
    for field in _PAGINATION_FIELDS:
        schema.get("properties", {}).pop(field, None)
    schema.pop("title", None)
    return schema


def _llm_schema() -> dict:
    """Wrapper schema: {hard: FiltersSchema, soft: FiltersSchema}."""
    filters = _filters_schema()
    return {
        "title": "QueryConstraints",
        "type": "object",
        "properties": {
            "hard": {**filters, "description": "Constraints that MUST be satisfied. Violations exclude a listing."},
            "soft": {**filters, "description": "Preferences that influence ranking. Violations do not exclude."},
        },
        "required": [],
    }


def _build_extractor():
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_openai import ChatOpenAI
    from .prompts import FEW_SHOT_MESSAGES, SYSTEM_PROMPT

    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    llm = ChatOpenAI(model=model, temperature=0, seed=42).with_structured_output(_llm_schema())
    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        *FEW_SHOT_MESSAGES,
        ("human", "{query}"),
    ])
    return prompt | llm


_extractor = None


def extract_constraints(query: str) -> QueryConstraints:
    global _extractor
    try:
        if _extractor is None:
            _extractor = _build_extractor()
        raw: dict = _extractor.invoke({"query": query})
        hard_raw = {k: v for k, v in raw.get("hard", {}).items() if k not in _PAGINATION_FIELDS}
        soft_raw = {k: v for k, v in raw.get("soft", {}).items() if k not in _PAGINATION_FIELDS}
        constraints = QueryConstraints(
            hard=HardFilters(**hard_raw),
            soft=QueryConstraints.SoftFilters(**soft_raw),
        )
        return enrich_constraints_with_geolocation(query, constraints)
    except Exception as exc:
        logger.error("Constraint extraction failed for query %r: %s", query, exc)
        return enrich_constraints_with_geolocation(query, QueryConstraints())
