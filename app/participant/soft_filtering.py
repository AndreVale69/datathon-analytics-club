from __future__ import annotations

from typing import Any


def filter_soft_facts(
    candidates: list[dict[str, Any]],
    soft: Any,
) -> list[dict[str, Any]]:
    """Soft constraints never exclude — all candidates pass through."""
    return candidates
