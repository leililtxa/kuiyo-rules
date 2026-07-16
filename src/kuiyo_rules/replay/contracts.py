from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal, Protocol

import pandas as pd

from kuiyo_rules.clauses import ClauseTrace
from kuiyo_rules.evidence import (
    DatasetQueryRequirement,
    InputEvidence,
    QueryIntent,
    ResolutionEvidence,
)
from kuiyo_rules.identifiers import require_key, require_sha256, require_version
from kuiyo_rules.serialization import FrozenJson, freeze_json


ReplayStatus = Literal["ok", "no_candidate", "invalid_input", "evaluator_error"]
ParityStatus = Literal["exact", "mismatch", "unavailable", "not_applicable"]


class RuleStageOutput(Protocol):
    status: str
    data_quality: str
    summary: Mapping[str, object]
    clause_traces: tuple[ClauseTrace, ...]


@dataclass(frozen=True)
class ReplayRequest:
    rule_key: str
    rule_version: str
    trade_dates: tuple[date, ...]

    def __post_init__(self) -> None:
        require_key(self.rule_key, field="rule_key")
        require_version(self.rule_version, field="rule_version")
        if not self.trade_dates:
            raise ValueError("trade_dates must not be empty")
        if len(set(self.trade_dates)) != len(self.trade_dates):
            raise ValueError("trade_dates must not contain duplicates")
        object.__setattr__(self, "trade_dates", tuple(self.trade_dates))


@dataclass(frozen=True)
class ReplayStageAttempt:
    stage_key: str
    attempt_key: str
    cutoff_at: datetime

    def __post_init__(self) -> None:
        require_key(self.stage_key, field="stage_key")
        require_key(self.attempt_key, field="attempt_key")
        _require_aware(self.cutoff_at, field="cutoff_at")


@dataclass(frozen=True)
class ReplayDayPlan:
    trade_date: date
    timezone: str
    attempts: tuple[ReplayStageAttempt, ...]

    def __post_init__(self) -> None:
        if not self.timezone.strip():
            raise ValueError("timezone must not be empty")
        if not self.attempts:
            raise ValueError("attempts must not be empty")
        identities = {(item.stage_key, item.attempt_key) for item in self.attempts}
        if len(identities) != len(self.attempts):
            raise ValueError("attempts must have unique stage_key/attempt_key identities")
        if any(item.cutoff_at.date() != self.trade_date for item in self.attempts):
            raise ValueError("attempt cutoff_at must belong to plan trade_date")
        object.__setattr__(self, "attempts", tuple(self.attempts))


@dataclass(frozen=True)
class ReplayPlan:
    rule_key: str
    rule_version: str
    rule_definition_hash: str
    days: tuple[ReplayDayPlan, ...]

    def __post_init__(self) -> None:
        require_key(self.rule_key, field="rule_key")
        require_version(self.rule_version, field="rule_version")
        require_sha256(self.rule_definition_hash, field="rule_definition_hash")
        if not self.days:
            raise ValueError("days must not be empty")
        if len({item.trade_date for item in self.days}) != len(self.days):
            raise ValueError("days must have unique trade_date values")
        object.__setattr__(self, "days", tuple(self.days))


@dataclass(frozen=True)
class ReplayStageInputPlan:
    rule_key: str
    rule_version: str
    rule_definition_hash: str
    trade_date: date
    attempt: ReplayStageAttempt
    requirements: tuple[DatasetQueryRequirement | QueryIntent, ...]

    def __post_init__(self) -> None:
        require_key(self.rule_key, field="rule_key")
        require_version(self.rule_version, field="rule_version")
        require_sha256(self.rule_definition_hash, field="rule_definition_hash")
        if self.attempt.cutoff_at.date() != self.trade_date:
            raise ValueError("attempt cutoff_at must match plan trade_date")
        input_keys = [_requirement_query(item).input_key for item in self.requirements]
        if len(set(input_keys)) != len(input_keys):
            raise ValueError("requirements must have unique input_key values")
        if any(
            isinstance(item, QueryIntent) and item.input_type != "stage_output"
            for item in self.requirements
        ):
            raise ValueError("Dataset requirements must use DatasetQueryRequirement")
        object.__setattr__(self, "requirements", tuple(self.requirements))

    @property
    def external_requirements(self) -> tuple[DatasetQueryRequirement, ...]:
        return tuple(
            item for item in self.requirements if isinstance(item, DatasetQueryRequirement)
        )

    @property
    def upstream_requirements(self) -> tuple[QueryIntent, ...]:
        return tuple(
            item
            for item in self.requirements
            if isinstance(item, QueryIntent) and item.input_type == "stage_output"
        )


@dataclass(frozen=True)
class ResolvedReplayDataset:
    input_key: str
    frame: pd.DataFrame
    resolution_evidence: ResolutionEvidence

    def __post_init__(self) -> None:
        require_key(self.input_key, field="input_key")
        if self.resolution_evidence.query.input_type != "dataset":
            raise ValueError("resolved replay data must be a Dataset input")
        if self.resolution_evidence.query.input_key != self.input_key:
            raise ValueError("resolved input_key must match evidence query input_key")


@dataclass(frozen=True)
class ResolvedReplayStageData:
    plan: ReplayStageInputPlan
    datasets: tuple[ResolvedReplayDataset, ...]

    def __post_init__(self) -> None:
        keys = [item.input_key for item in self.datasets]
        if len(set(keys)) != len(keys):
            raise ValueError("datasets must have unique input_key values")
        required = {item.query.input_key for item in self.plan.external_requirements}
        resolved = set(keys)
        if required != resolved:
            raise ValueError("resolved datasets must exactly match external requirements")
        requirements = {
            item.query.input_key: item.query for item in self.plan.external_requirements
        }
        for dataset in self.datasets:
            planned = requirements[dataset.input_key]
            actual = dataset.resolution_evidence.query
            if (
                planned.dataset_key,
                planned.fields,
                planned.filters,
                planned.symbol_count,
                planned.symbol_set_fingerprint,
                planned.missing_policy,
            ) != (
                actual.dataset_key,
                actual.fields,
                actual.filters,
                actual.symbol_count,
                actual.symbol_set_fingerprint,
                actual.missing_policy,
            ):
                raise ValueError("resolved Dataset evidence does not match planned query")
        object.__setattr__(self, "datasets", tuple(self.datasets))


@dataclass(frozen=True)
class ReplayStageResult:
    attempt: ReplayStageAttempt
    status: str
    data_quality: str
    rule_output: RuleStageOutput
    clause_traces: tuple[ClauseTrace, ...]
    input_evidence: tuple[InputEvidence, ...]
    typed_input_fingerprint: str | None = None
    rule_output_fingerprint: str | None = None
    clause_trace_fingerprint: str | None = None

    def __post_init__(self) -> None:
        if not self.status.strip() or not self.data_quality.strip():
            raise ValueError("status and data_quality must not be empty")
        for field_name in (
            "typed_input_fingerprint",
            "rule_output_fingerprint",
            "clause_trace_fingerprint",
        ):
            value = getattr(self, field_name)
            if value is not None:
                require_sha256(value, field=field_name)
        object.__setattr__(self, "clause_traces", tuple(self.clause_traces))
        object.__setattr__(self, "input_evidence", tuple(self.input_evidence))


@dataclass(frozen=True)
class ReplayProgress:
    plan: ReplayDayPlan
    completed_stages: tuple[ReplayStageResult, ...] = ()
    processed_attempt_count: int | None = None

    def __post_init__(self) -> None:
        processed_attempt_count = (
            len(self.completed_stages)
            if self.processed_attempt_count is None
            else self.processed_attempt_count
        )
        if not 0 <= processed_attempt_count <= len(self.plan.attempts):
            raise ValueError("processed_attempt_count is outside the replay plan")
        if len(self.completed_stages) > processed_attempt_count:
            raise ValueError("completed stages cannot exceed processed attempts")
        positions = {attempt: index for index, attempt in enumerate(self.plan.attempts)}
        completed_positions = [positions.get(result.attempt) for result in self.completed_stages]
        if any(position is None for position in completed_positions):
            raise ValueError("completed stage is not part of the replay plan")
        if completed_positions != sorted(completed_positions) or any(
            position >= processed_attempt_count for position in completed_positions
        ):
            raise ValueError("completed stages must follow processed attempt order")
        object.__setattr__(self, "completed_stages", tuple(self.completed_stages))
        object.__setattr__(self, "processed_attempt_count", processed_attempt_count)

    @property
    def is_complete(self) -> bool:
        return self.processed_attempt_count == len(self.plan.attempts)

    @property
    def next_attempt(self) -> ReplayStageAttempt | None:
        return None if self.is_complete else self.plan.attempts[self.processed_attempt_count]

    def advance(self, result: ReplayStageResult) -> ReplayProgress:
        expected = self.next_attempt
        if expected is None:
            raise ValueError("cannot advance a completed replay")
        if result.attempt != expected:
            raise ValueError("stage result does not match next planned attempt")
        return ReplayProgress(
            self.plan,
            (*self.completed_stages, result),
            self.processed_attempt_count + 1,
        )

    def skip_next(self) -> ReplayProgress:
        if self.next_attempt is None:
            raise ValueError("cannot skip a completed replay")
        return ReplayProgress(
            self.plan,
            self.completed_stages,
            self.processed_attempt_count + 1,
        )


@dataclass(frozen=True)
class ReplayDayResult:
    rule_key: str
    rule_version: str
    rule_definition_hash: str
    trade_date: date
    stages: tuple[ReplayStageResult, ...]
    status: ReplayStatus
    data_quality: str
    semantic_fingerprint: str
    errors: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require_key(self.rule_key, field="rule_key")
        require_version(self.rule_version, field="rule_version")
        require_sha256(self.rule_definition_hash, field="rule_definition_hash")
        require_sha256(self.semantic_fingerprint, field="semantic_fingerprint")
        if self.status not in {"ok", "no_candidate", "invalid_input", "evaluator_error"}:
            raise ValueError(f"unsupported replay status: {self.status}")
        if not self.data_quality.strip():
            raise ValueError("data_quality must not be empty")
        identities = {(item.attempt.stage_key, item.attempt.attempt_key) for item in self.stages}
        if len(identities) != len(self.stages):
            raise ValueError("stages must have unique stage/attempt identities")
        if any(item.attempt.cutoff_at.date() != self.trade_date for item in self.stages):
            raise ValueError("stage attempt must match replay trade_date")
        object.__setattr__(self, "stages", tuple(self.stages))
        object.__setattr__(self, "errors", tuple(self.errors))

    @property
    def clause_traces(self) -> tuple[ClauseTrace, ...]:
        return tuple(trace for stage in self.stages for trace in stage.clause_traces)

    @property
    def stage_results(self) -> tuple[ReplayStageResult, ...]:
        return self.stages

    @property
    def definition_hash(self) -> str:
        return self.rule_definition_hash


@dataclass(frozen=True)
class ReplayResult:
    rule_key: str
    rule_version: str
    rule_definition_hash: str
    days: tuple[ReplayDayResult, ...]
    summary: Mapping[str, FrozenJson]

    def __post_init__(self) -> None:
        require_key(self.rule_key, field="rule_key")
        require_version(self.rule_version, field="rule_version")
        require_sha256(self.rule_definition_hash, field="rule_definition_hash")
        if not self.days:
            raise ValueError("days must not be empty")
        if len({item.trade_date for item in self.days}) != len(self.days):
            raise ValueError("days must have unique trade_date values")
        if any(
            (item.rule_key, item.rule_version, item.rule_definition_hash)
            != (self.rule_key, self.rule_version, self.rule_definition_hash)
            for item in self.days
        ):
            raise ValueError("replay day identity must match result identity")
        frozen = freeze_json(self.summary, path="summary")
        if not isinstance(frozen, Mapping):
            raise TypeError("summary must be an object")
        object.__setattr__(self, "days", tuple(self.days))
        object.__setattr__(self, "summary", frozen)


def _require_aware(value: datetime, *, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")


def _requirement_query(
    requirement: DatasetQueryRequirement | QueryIntent,
) -> QueryIntent:
    return requirement.query if isinstance(requirement, DatasetQueryRequirement) else requirement
