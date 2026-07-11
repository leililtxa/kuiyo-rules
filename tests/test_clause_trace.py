from __future__ import annotations

from types import MappingProxyType

import pytest

from kuiyo_rules import ClauseTrace


def test_clause_trace_freezes_payload_and_serializes() -> None:
    trace = ClauseTrace(
        clause_key="opening.stock-eligibility",
        clause_version="v001",
        stage_key="generate",
        attempt_key="2026-06-22T09:36:00+08:00",
        subject_type="stock",
        subject_key="600001.SH",
        evaluation_status="evaluated",
        inputs={"return": 0.01},
        output={"pass": True},
        reason_codes=("passed",),
    )

    assert isinstance(trace.inputs, MappingProxyType)
    assert trace.to_payload()["subject_key"] == "600001.SH"
    with pytest.raises(TypeError):
        trace.inputs["return"] = 0.02  # type: ignore[index]


def test_clause_trace_rejects_non_finite_payload() -> None:
    with pytest.raises(ValueError, match="NaN or infinity"):
        ClauseTrace(
            clause_key="opening.stock-eligibility",
            clause_version="v001",
            stage_key="generate",
            attempt_key="attempt-1",
            subject_type="stock",
            subject_key="600001.SH",
            evaluation_status="evaluated",
            inputs={"return": float("nan")},
            output={},
        )
