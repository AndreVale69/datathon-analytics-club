from __future__ import annotations

import copy
from concurrent.futures import ThreadPoolExecutor
import json
import logging
from typing import Any, get_args

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from app.models.schemas import FeatureName, HardFilters, QueryConstraints
from app.participant.llm_client import build_json_prompt_extractor
from app.participant.geolocation_extractor import (
    GeolocationConstraints,
    apply_geolocation_constraints,
    extract_geolocation_constraints,
)
from project_env import load_project_env

load_project_env()

logger = logging.getLogger(__name__)

_PAGINATION_FIELDS = {"limit", "offset", "sort_by"}
_GEO_FIELDS = {"latitude", "longitude", "radius_km", "geo_targets"}
_VALID_FEATURES = set(get_args(FeatureName))
_EXTRACTION_POOL = ThreadPoolExecutor(max_workers=3, thread_name_prefix="constraint-extract")


def _schema_without_fields(model: type[HardFilters]) -> dict[str, Any]:
    schema = copy.deepcopy(model.model_json_schema())
    for field in _PAGINATION_FIELDS | _GEO_FIELDS:
        schema.get("properties", {}).pop(field, None)
    schema.pop("title", None)
    return schema


def _hard_schema() -> dict[str, Any]:
    return _schema_without_fields(HardFilters)


def _soft_schema() -> dict[str, Any]:
    return _schema_without_fields(QueryConstraints.SoftFilters)


def _select_few_shots(field_name: str) -> list[BaseMessage]:
    from .prompts import FEW_SHOT_MESSAGES

    selected: list[BaseMessage] = []
    for index in range(0, len(FEW_SHOT_MESSAGES), 2):
        human = FEW_SHOT_MESSAGES[index]
        assistant = FEW_SHOT_MESSAGES[index + 1]
        parsed = json.loads(assistant.content)
        selected.append(HumanMessage(content=human.content))
        selected.append(AIMessage(content=json.dumps(parsed.get(field_name, {}), ensure_ascii=True)))
    return selected


def _hard_system_prompt() -> str:
    from .prompts import SYSTEM_PROMPT

    return (
        SYSTEM_PROMPT
        + "\n\nTask: extract only HARD constraints."
        + "\nReturn a single JSON object matching the provided schema."
        + "\nDo not include soft preferences."
        + "\nDo not include geolocation coordinates or radius fields."
    )


def _soft_system_prompt() -> str:
    from .prompts import SYSTEM_PROMPT

    return (
        SYSTEM_PROMPT
        + "\n\nTask: extract only SOFT preferences."
        + "\nReturn a single JSON object matching the provided schema."
        + "\nDo not include hard constraints unless they are clearly preference-like."
        + "\nDo not include geolocation coordinates or radius fields."
    )


def _sanitize_filter_payload(payload: dict[str, Any]) -> dict[str, Any]:
    sanitized = {
        key: value
        for key, value in payload.items()
        if key not in _PAGINATION_FIELDS and key not in _GEO_FIELDS
    }
    features = sanitized.get("features")
    if isinstance(features, list):
        kept = [feature for feature in features if feature in _VALID_FEATURES]
        sanitized["features"] = kept or None
    _sanitize_range_pair(sanitized, "min_price", "max_price")
    _sanitize_range_pair(sanitized, "min_rooms", "max_rooms")
    _sanitize_range_pair(sanitized, "min_area", "max_area")
    return sanitized


def _sanitize_range_pair(payload: dict[str, Any], lower_key: str, upper_key: str) -> None:
    lower = payload.get(lower_key)
    upper = payload.get(upper_key)
    if lower is None or upper is None:
        return
    try:
        if lower > upper:
            payload[lower_key], payload[upper_key] = upper, lower
    except TypeError:
        payload[lower_key] = None
        payload[upper_key] = None


def _deduplicate_overlaps(constraints: QueryConstraints) -> QueryConstraints:
    merged = constraints.model_copy(deep=True)
    if merged.hard.city and merged.soft.city:
        hard_cities = {city.casefold() for city in merged.hard.city}
        merged.soft.city = [city for city in merged.soft.city if city.casefold() not in hard_cities] or None
    if merged.hard.object_category and merged.soft.object_category:
        hard_categories = set(merged.hard.object_category)
        merged.soft.object_category = [
            category for category in merged.soft.object_category if category not in hard_categories
        ] or None
    if merged.hard.features and merged.soft.features:
        hard_features = set(merged.hard.features)
        merged.soft.features = [feature for feature in merged.soft.features if feature not in hard_features] or None
    return merged


def _build_hard_extractor():
    return build_json_prompt_extractor(
        system_prompt=_hard_system_prompt(),
        schema=_hard_schema(),
        few_shot_messages=_select_few_shots("hard"),
        provider_env_var="HARD_CONSTRAINTS_PROVIDER",
        openai_model_env_var="HARD_CONSTRAINTS_OPENAI_MODEL",
        bedrock_model_env_var="HARD_CONSTRAINTS_BEDROCK_MODEL_ID",
        default_provider="openai",
        default_openai_model="gpt-5-mini",
        default_bedrock_model="us.anthropic.claude-sonnet-4-5-20250929-v1:0",
    )


def _build_soft_extractor():
    return build_json_prompt_extractor(
        system_prompt=_soft_system_prompt(),
        schema=_soft_schema(),
        few_shot_messages=_select_few_shots("soft"),
        provider_env_var="SOFT_PREFERENCES_PROVIDER",
        openai_model_env_var="SOFT_PREFERENCES_OPENAI_MODEL",
        bedrock_model_env_var="SOFT_PREFERENCES_BEDROCK_MODEL_ID",
        default_provider="openai",
        default_openai_model="gpt-5-mini",
        default_bedrock_model="us.anthropic.claude-sonnet-4-5-20250929-v1:0",
    )


_extractor = None
_hard_extractor = None
_soft_extractor = None


def extract_constraints(query: str) -> QueryConstraints:
    global _extractor, _hard_extractor, _soft_extractor
    try:
        if _extractor is not None:
            raw: dict[str, Any] = _extractor.invoke({"query": query})
            hard_raw = _sanitize_filter_payload(raw.get("hard", {}))
            soft_raw = _sanitize_filter_payload(raw.get("soft", {}))
            geo = extract_geolocation_constraints(query)
        else:
            if _hard_extractor is None:
                _hard_extractor = _build_hard_extractor()
            if _soft_extractor is None:
                _soft_extractor = _build_soft_extractor()
            hard_future = _EXTRACTION_POOL.submit(_safe_stage_invoke, _hard_extractor, {"query": query}, "hard", query)
            soft_future = _EXTRACTION_POOL.submit(_safe_stage_invoke, _soft_extractor, {"query": query}, "soft", query)
            geo_future = _EXTRACTION_POOL.submit(_safe_geolocation_extract, query)
            hard_raw = _sanitize_filter_payload(hard_future.result())
            soft_raw = _sanitize_filter_payload(soft_future.result())
            geo = geo_future.result()
        constraints = QueryConstraints(
            hard=HardFilters(**hard_raw),
            soft=QueryConstraints.SoftFilters(**soft_raw),
        )
        return _deduplicate_overlaps(apply_geolocation_constraints(constraints, geo))
    except Exception as exc:
        logger.error("Constraint extraction failed for query %r: %s", query, exc)
        return apply_geolocation_constraints(QueryConstraints(), extract_geolocation_constraints(query))


def _coerce_geolocation_constraints(value: Any) -> GeolocationConstraints:
    if isinstance(value, GeolocationConstraints):
        return value
    return GeolocationConstraints()


def _safe_stage_invoke(extractor: Any, payload: dict[str, str], stage_name: str, query: str) -> dict[str, Any]:
    try:
        raw = extractor.invoke(payload)
        if isinstance(raw, dict):
            return raw
    except Exception as exc:
        logger.warning("%s extraction failed for query %r: %s", stage_name, query, exc)
    return {}


def _safe_geolocation_extract(query: str) -> GeolocationConstraints:
    try:
        return _coerce_geolocation_constraints(extract_geolocation_constraints(query))
    except Exception as exc:
        logger.warning("geolocation extraction failed for query %r: %s", query, exc)
        return GeolocationConstraints()
