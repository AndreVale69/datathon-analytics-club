from __future__ import annotations

from typing import Any, List
import logging
from pathlib import Path

import numpy as np

from .description_artifacts import load_listing_embeddings

logger = logging.getLogger(__name__)

_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
_model = None

_cached_listing_index = None
_cached_listing_embs = None


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(_MODEL_NAME)
    return _model


def _load_listing_artifacts(artifacts_dir: Path | str = "artifacts") -> bool:
    global _cached_listing_index, _cached_listing_embs
    if _cached_listing_index is None or _cached_listing_embs is None:
        loaded = load_listing_embeddings(artifacts_dir)
        if loaded is None:
            logger.debug("Listing artifacts not available in %s", artifacts_dir)
            return False
        _cached_listing_index, _cached_listing_embs, _ = loaded
    return True


def compute_query_similarities(
    query: str,
    candidates: List[dict[str, Any]],
    *,
    artifacts_dir: Path | str = "artifacts",
) -> dict[str, float]:
    """Return {listing_id: cosine_similarity} between query and precomputed description embeddings.

    Embeddings are L2-normalized so cosine similarity equals the dot product.
    Returns an empty dict if artifacts are missing or any error occurs.
    """
    try:
        if not _load_listing_artifacts(artifacts_dir):
            return {}

        model = _get_model()
        q_emb = model.encode([query], normalize_embeddings=True, convert_to_numpy=True)[0]  # (d,)

        result: dict[str, float] = {}
        for c in candidates:
            lid = str(c.get("listing_id", ""))
            if not lid:
                continue
            row = _cached_listing_index.get(lid)
            if row is None:
                continue
            result[lid] = float(np.dot(_cached_listing_embs[row], q_emb))

        return result
    except Exception:
        logger.exception("Error during compute_query_similarities")
        return {}
