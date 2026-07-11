from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Literal

from kuiyo_rules.identifiers import require_key, require_version
from kuiyo_rules.serialization import FrozenJson, freeze_json, thaw_json


TraceEvaluationStatus = Literal["evaluated", "skipped", "unavailable", "error"]


@dataclass(frozen=True)
class ClauseTrace:
    clause_key: str
    clause_version: str
    stage_key: str
    attempt_key: str
    subject_type: str
    subject_key: str
    evaluation_status: TraceEvaluationStatus
    inputs: Mapping[str, FrozenJson]
    output: Mapping[str, FrozenJson]
    reason_codes: tuple[str, ...] = ()
    data_quality: str = "normal"

    def __post_init__(self) -> None:
        require_key(self.clause_key, field="clause_key")
        require_version(self.clause_version, field="clause_version")
        require_key(self.stage_key, field="stage_key")
        require_key(self.subject_type, field="subject_type")
        if not self.attempt_key.strip():
            raise ValueError("attempt_key must not be empty")
        if not self.subject_key.strip():
            raise ValueError("subject_key must not be empty")
        if self.evaluation_status not in {"evaluated", "skipped", "unavailable", "error"}:
            raise ValueError(f"unsupported trace evaluation status: {self.evaluation_status}")
        if not self.data_quality.strip():
            raise ValueError("data_quality must not be empty")
        inputs = freeze_json(dict(self.inputs), path="trace.inputs")
        output = freeze_json(dict(self.output), path="trace.output")
        if not isinstance(inputs, Mapping) or not isinstance(output, Mapping):
            raise TypeError("trace inputs/output must be objects")
        reasons = tuple(str(reason) for reason in self.reason_codes if str(reason))
        object.__setattr__(self, "inputs", MappingProxyType(dict(inputs)))
        object.__setattr__(self, "output", MappingProxyType(dict(output)))
        object.__setattr__(self, "reason_codes", reasons)

    def to_payload(self) -> dict[str, Any]:
        return {
            "clause_key": self.clause_key,
            "clause_version": self.clause_version,
            "stage_key": self.stage_key,
            "attempt_key": self.attempt_key,
            "subject_type": self.subject_type,
            "subject_key": self.subject_key,
            "evaluation_status": self.evaluation_status,
            "inputs": thaw_json(self.inputs),
            "output": thaw_json(self.output),
            "reason_codes": list(self.reason_codes),
            "data_quality": self.data_quality,
        }


def freeze_traces(traces: Sequence[ClauseTrace]) -> tuple[ClauseTrace, ...]:
    return tuple(traces)
