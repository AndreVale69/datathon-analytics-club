from __future__ import annotations

from typing import Any
from app.models.schemas import HardFilters


def filter_soft_facts(
    candidates: list[dict[str, Any]],
    soft: HardFilters,
) -> list[dict[str, Any]]:
    # Soft constraints never exclude — all candidates pass through.
    # The soft object is available for future pre-filtering logic here.
    return candidates
