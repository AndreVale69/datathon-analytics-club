from __future__ import annotations

import json
import logging
from pathlib import Path

from app.core.hard_filters import search_listings
from app.harness.search_service import to_hard_filter_params
from app.models.schemas import QueryConstraints
from app.participant.constraint_extractor import extract_constraints
from app.participant.description_analysis import compute_query_similarities
from app.participant.description_extractor import extract_features_from_descriptions
from app.participant.llm_client import build_text_prompt_generator
from app.participant.ranking import build_score_breakdown, rank_listings

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You explain apartment-search ranking results.

Your job is to explain why one listing received its score using only the structured ranking evidence provided.

Rules:
- Stay grounded in the evidence.
- Be concise: 3 to 5 sentences.
- Mention the strongest positive factors first.
- Mention the biggest downside if there is one.
- If comparison data is provided, explain why this listing ranked above or below the nearby alternative.
- Do not mention internal implementation details unless they help the user understand the tradeoff.
- Do not invent facts about the property.
"""

_generator = None


def explain_listing_match(*, db_path: Path, query: str, listing_id: str) -> str:
    constraints = extract_constraints(query)
    constraints.hard.limit = 500
    constraints.hard.offset = 0

    candidates = search_listings(db_path, to_hard_filter_params(constraints.hard))
    query_similarities = compute_query_similarities(query, candidates)
    extracted_features = extract_features_from_descriptions(candidates, query_similarities)
    ranked = rank_listings(candidates, constraints.soft, constraints.hard, query_similarities, extracted_features)

    current_index = next((index for index, item in enumerate(ranked) if item.listing_id == listing_id), None)
    if current_index is None:
        raise LookupError(f"Listing {listing_id} not found in ranked results for query.")

    selected_candidate = next(candidate for candidate in candidates if str(candidate["listing_id"]) == listing_id)
    selected_breakdown = build_score_breakdown(
        selected_candidate,
        constraints.soft,
        constraints.hard,
        query_similarities.get(listing_id, 0.0),
        extracted_features.get(listing_id),
    )

    comparison_payload = None
    if current_index > 0:
        comparison_result = ranked[current_index - 1]
        comparison_candidate = next(
            candidate for candidate in candidates if str(candidate["listing_id"]) == comparison_result.listing_id
        )
        comparison_payload = {
            "rank": current_index,
            "listing_id": comparison_result.listing_id,
            "title": comparison_result.listing.title,
            "score_breakdown": build_score_breakdown(
                comparison_candidate,
                constraints.soft,
                constraints.hard,
                query_similarities.get(comparison_result.listing_id, 0.0),
                extracted_features.get(comparison_result.listing_id),
            ),
        }

    payload = {
        "query": query,
        "selected_listing": {
            "rank": current_index + 1,
            "listing_id": listing_id,
            "title": ranked[current_index].listing.title,
            "score_breakdown": selected_breakdown,
            "existing_reason": ranked[current_index].reason,
        },
        "hard_constraints": constraints.hard.model_dump(exclude_none=True, exclude_defaults=True),
        "soft_preferences": constraints.soft.model_dump(exclude_none=True, exclude_defaults=True),
        "comparison_with_listing_above": comparison_payload,
    }

    try:
        return _get_generator().invoke(json.dumps(payload, ensure_ascii=False, indent=2))
    except Exception as exc:
        logger.warning("Explanation generation failed for listing %r and query %r: %s", listing_id, query, exc)
        return ranked[current_index].reason


def _get_generator():
    global _generator
    if _generator is None:
        _generator = build_text_prompt_generator(
            system_prompt=_SYSTEM_PROMPT,
            provider_env_var="EXPLANATION_PROVIDER",
            openai_model_env_var="EXPLANATION_OPENAI_MODEL",
            bedrock_model_env_var="EXPLANATION_BEDROCK_MODEL_ID",
            default_provider="bedrock",
            default_openai_model="gpt-5-mini",
            default_bedrock_model="us.anthropic.claude-sonnet-4-5-20250929-v1:0",
        )
    return _generator
