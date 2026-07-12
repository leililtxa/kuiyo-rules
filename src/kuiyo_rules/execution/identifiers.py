from __future__ import annotations

from datetime import datetime


def canonical_attempt_key(stage_key: str, decision_cutoff_at: datetime) -> str:
    normalized_stage = stage_key.strip()
    if not normalized_stage:
        raise ValueError("stage_key must not be empty")
    if decision_cutoff_at.tzinfo is None or decision_cutoff_at.utcoffset() is None:
        raise ValueError("decision_cutoff_at must be timezone-aware")
    return f"{normalized_stage}.{decision_cutoff_at:%H%M}"
