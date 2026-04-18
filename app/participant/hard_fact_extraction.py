from __future__ import annotations

from app.models.schemas import HardFilters
from app.participant.constraint_extractor import extract_constraints


def extract_hard_facts(query: str) -> HardFilters:
    return extract_constraints(query)
