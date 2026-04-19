"""LLM-based feature extractor for listing descriptions.

Runs only on candidates whose query-description cosine similarity exceeds
SIMILARITY_THRESHOLD, keeping the number of LLM calls small.
Descriptions are batched (_BATCH_SIZE per call) to minimise latency.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel

from app.participant.llm_client import JsonPromptExtractor

logger = logging.getLogger(__name__)

SIMILARITY_THRESHOLD = 0.35
_MAX_CANDIDATES = 10     # process at most this many descriptions per request
_MAX_DESC_CHARS = 1500   # truncate long descriptions to keep tokens bounded


class ExtractedFeatures(BaseModel):
    # ── Physical / structural ────────────────────────────────────────────────
    bedrooms: int | None = None
    bathrooms: int | None = None
    has_garden: bool | None = None
    has_balcony: bool | None = None
    has_terrace: bool | None = None
    has_rooftop: bool | None = None
    has_cellar: bool | None = None
    has_bathtub: bool | None = None
    has_view: bool | None = None
    floor: int | None = None          # 0 = ground floor
    not_ground_floor: bool | None = None
    furnished: bool | None = None
    # ── Interior / aesthetic ─────────────────────────────────────────────────
    is_bright: bool | None = None     # lots of light / bright rooms
    is_modern: bool | None = None     # modern / recently renovated
    good_layout: bool | None = None   # good floor plan / efficient layout
    # ── Neighbourhood / environment ──────────────────────────────────────────
    is_quiet: bool | None = None      # quiet location / street
    near_lake: bool | None = None     # near a lake
    safe_area: bool | None = None     # safe / secure neighbourhood
    good_schools: bool | None = None  # good schools nearby
    low_traffic: bool | None = None   # low traffic / not on a major road
    green_space: bool | None = None   # parks / greenery nearby
    walkable_shopping: bool | None = None  # shops within walking distance
    good_transport: bool | None = None    # good public transport access
    family_friendly: bool | None = None   # family-friendly environment
    playground_nearby: bool | None = None # playground / Spielplatz nearby


_SYSTEM_PROMPT = """\
You are a real-estate feature extractor.

You receive one or more listing descriptions, each prefixed by its listing_id in brackets.
Extract features from each description and return a single JSON object where:
  - each key is the listing_id (as a string)
  - each value is an object containing ONLY the fields you can confidently extract

PHYSICAL / STRUCTURAL fields (omit if not mentioned):
  bedrooms         : int  — number of bedrooms / Schlafzimmer / chambres
  bathrooms        : int  — number of bathrooms or WCs (combined)
  has_garden       : bool — private garden / Garten / jardin
  has_balcony      : bool — balcony / Balkon / balcon
  has_terrace      : bool — terrace (larger than balcony) / Terrasse
  has_rooftop      : bool — rooftop terrace / Dachterrasse
  has_cellar       : bool — cellar or storage room / Keller / cave
  has_bathtub      : bool — bathtub / Badewanne / baignoire
  has_view         : bool — notable view (lake, mountains, city skyline)
  floor            : int  — floor number (0 = ground floor / Erdgeschoss)
  not_ground_floor : bool — explicitly not on ground floor
  furnished        : bool — furnished / möbliert / meublé

INTERIOR / AESTHETIC fields:
  is_bright   : bool — described as bright, lots of light, large windows / hell, viel Licht, große Fenster
  is_modern   : bool — described as modern, renovated, contemporary / modern, renoviert, Neubau
  good_layout : bool — described as good layout, practical plan, well-designed / guter Schnitt, gute Raumaufteilung

NEIGHBOURHOOD / ENVIRONMENT fields:
  is_quiet          : bool — quiet location, quiet street / ruhige Lage, ruhige Straße
  near_lake         : bool — near a lake / in Seenähe, am See
  safe_area         : bool — safe, secure neighbourhood / sicheres Quartier, sichere Gegend
  good_schools      : bool — good schools nearby / gute Schulen, gute Schulanbindung
  low_traffic       : bool — low traffic, not on a main road / wenig Verkehr, keine Durchgangsstraße
  green_space       : bool — parks, greenery nearby / Parks, Grün, Natur in der Nähe
  walkable_shopping : bool — shops within walking distance / Einkaufen zu Fuß, Läden fußläufig
  good_transport    : bool — good public transport / gute ÖV-Anbindung, nahe Haltestelle
  family_friendly   : bool — family-friendly environment / familienfreundlich, kinderfreundlich
  playground_nearby : bool — playground nearby / Spielplatz in der Nähe

Return ONLY valid JSON. No markdown fences.
"""

_SCHEMA: dict[str, Any] = {
    "type": "object",
    "description": "Map of listing_id → extracted features",
    "additionalProperties": {
        "type": "object",
        "properties": {
            "bedrooms":          {"type": "integer"},
            "bathrooms":         {"type": "integer"},
            "has_garden":        {"type": "boolean"},
            "has_balcony":       {"type": "boolean"},
            "has_terrace":       {"type": "boolean"},
            "has_rooftop":       {"type": "boolean"},
            "has_cellar":        {"type": "boolean"},
            "has_bathtub":       {"type": "boolean"},
            "has_view":          {"type": "boolean"},
            "floor":             {"type": "integer"},
            "not_ground_floor":  {"type": "boolean"},
            "furnished":         {"type": "boolean"},
            "is_bright":         {"type": "boolean"},
            "is_modern":         {"type": "boolean"},
            "good_layout":       {"type": "boolean"},
            "is_quiet":          {"type": "boolean"},
            "near_lake":         {"type": "boolean"},
            "safe_area":         {"type": "boolean"},
            "good_schools":      {"type": "boolean"},
            "low_traffic":       {"type": "boolean"},
            "green_space":       {"type": "boolean"},
            "walkable_shopping": {"type": "boolean"},
            "good_transport":    {"type": "boolean"},
            "family_friendly":   {"type": "boolean"},
            "playground_nearby": {"type": "boolean"},
        },
    },
}

_VALID_FIELDS = set(ExtractedFeatures.model_fields)

_extractor = None


def _get_extractor():
    global _extractor
    if _extractor is None:
        _extractor = JsonPromptExtractor(
            system_prompt=_SYSTEM_PROMPT,
            schema=_SCHEMA,
            few_shot_messages=[],
            provider="bedrock",
        )
    return _extractor


def _build_batch_query(batch: list[tuple[str, str]]) -> str:
    parts = []
    for lid, text in batch:
        parts.append(f"[{lid}]\n{text[:_MAX_DESC_CHARS].strip()}")
    return "\n\n".join(parts)


def extract_features_from_descriptions(
    candidates: list[dict[str, Any]],
    query_similarities: dict[str, float],
    *,
    threshold: float = SIMILARITY_THRESHOLD,
) -> dict[str, ExtractedFeatures]:
    """Return {listing_id: ExtractedFeatures} for candidates above the similarity threshold.

    Listings below the threshold or with no description are skipped entirely.
    Returns an empty dict if no candidates qualify or on unrecoverable error.
    """
    eligible: list[tuple[str, str]] = []
    for c in candidates:
        lid = str(c.get("listing_id", ""))
        if not lid:
            continue
        if query_similarities.get(lid, 0.0) < threshold:
            continue
        text = (c.get("object_description") or c.get("description") or "").strip()
        if not text:
            continue
        eligible.append((lid, text))

    if not eligible:
        return {}

    eligible = eligible[:_MAX_CANDIDATES]

    result: dict[str, ExtractedFeatures] = {}
    try:
        raw: dict = _get_extractor().invoke({"query": _build_batch_query(eligible)})
        for lid, feats in raw.items():
            if not isinstance(feats, dict):
                continue
            try:
                result[lid] = ExtractedFeatures(**{
                    k: v for k, v in feats.items() if k in _VALID_FIELDS
                })
            except Exception:
                logger.debug("Could not parse extracted features for listing %s", lid)
    except Exception:
        logger.exception("Feature extraction LLM call failed")

    logger.debug(
        "Extracted features for %d/%d eligible candidates (threshold=%.2f)",
        len(result), len(eligible), threshold,
    )
    return result
