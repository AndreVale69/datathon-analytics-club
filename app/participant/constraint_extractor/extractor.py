from __future__ import annotations

import copy
import logging
import os

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI

from project_env import load_project_env
from app.models.schemas import HardFilters
from .prompts import FEW_SHOT_MESSAGES, SYSTEM_PROMPT

load_project_env()

logger = logging.getLogger(__name__)

# Pagination fields are not constraints — hide them from the LLM schema.
_PAGINATION_FIELDS = {"limit", "offset", "sort_by"}


def _llm_schema() -> dict:
    schema = copy.deepcopy(HardFilters.model_json_schema())
    for field in _PAGINATION_FIELDS:
        schema.get("properties", {}).pop(field, None)
    return schema


def _build_extractor() -> Runnable:
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    llm = ChatOpenAI(
        model=model,
        temperature=0,
        seed=42,
    ).with_structured_output(_llm_schema())

    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        *FEW_SHOT_MESSAGES,
        ("human", "{query}"),
    ])

    return prompt | llm


_extractor: Runnable | None = None


def extract_constraints(query: str) -> HardFilters:
    global _extractor
    if _extractor is None:
        _extractor = _build_extractor()
    try:
        raw: dict = _extractor.invoke({"query": query})
        return HardFilters(**{k: v for k, v in raw.items() if k not in _PAGINATION_FIELDS})
    except Exception as exc:
        logger.error("Constraint extraction failed for query %r: %s", query, exc)
        return HardFilters()
