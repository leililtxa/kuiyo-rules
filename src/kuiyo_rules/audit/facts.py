from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Literal

from kuiyo_rules.audit.identifiers import require_audit_spec_key
from kuiyo_rules.identifiers import require_key, require_sha256, require_version
from kuiyo_rules.serialization import FrozenJson, freeze_json


EvidenceCohort = Literal["strict", "quality_stratified", "invalid"]
MaturityStatus = Literal["pending", "mature", "invalid", "unavailable"]
ComputationMode = Literal["initial", "recomputed"]
StatisticsStatus = Literal["available", "insufficient_sample"]
ParityStatus = Literal["exact", "mismatch", "unavailable", "not_applicable"]


@dataclass(frozen=True)
class AuditIdentity:
    rule_key: str
    rule_version: str
    rule_definition_hash: str
    audit_spec_key: str
    audit_spec_version: str
    audit_spec_definition_hash: str

    def __post_init__(self) -> None:
        require_key(self.rule_key, field="rule_key")
        require_version(self.rule_version, field="rule_version")
        require_sha256(self.rule_definition_hash, field="rule_definition_hash")
        require_audit_spec_key(self.audit_spec_key)
        require_version(self.audit_spec_version, field="audit_spec_version")
        require_sha256(self.audit_spec_definition_hash, field="audit_spec_definition_hash")


@dataclass(frozen=True)
class ReplayDayFact:
    identity: AuditIdentity
    trade_date: date
    replay_status: str
    data_quality: str
    evidence_cohort: EvidenceCohort
    candidate_count: int
    generate_attempt_count: int
    completed_stage_count: int
    semantic_fingerprint: str
    stage_parity_status: ParityStatus
    input_parity_status: ParityStatus
    first_primary_cutoff_at: datetime | None = None
    errors: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.replay_status.strip() or not self.data_quality.strip():
            raise ValueError("replay_status and data_quality must not be empty")
        if self.evidence_cohort not in {"strict", "quality_stratified", "invalid"}:
            raise ValueError(f"unsupported evidence_cohort: {self.evidence_cohort}")
        _require_non_negative(
            candidate_count=self.candidate_count,
            generate_attempt_count=self.generate_attempt_count,
            completed_stage_count=self.completed_stage_count,
        )
        require_sha256(self.semantic_fingerprint, field="semantic_fingerprint")
        _require_parity(self.stage_parity_status, field="stage_parity_status")
        _require_parity(self.input_parity_status, field="input_parity_status")
        if self.first_primary_cutoff_at is not None:
            _require_aware(self.first_primary_cutoff_at, field="first_primary_cutoff_at")
            if self.first_primary_cutoff_at.date() != self.trade_date:
                raise ValueError("first_primary_cutoff_at must belong to trade_date")
        object.__setattr__(self, "errors", tuple(self.errors))


@dataclass(frozen=True)
class ReplayStageFact:
    trade_date: date
    stage_key: str
    attempt_key: str
    decision_cutoff_at: datetime
    stage_status: str
    data_quality: str
    typed_input_fingerprint: str | None
    rule_output_fingerprint: str | None
    clause_trace_fingerprint: str | None
    input_parity_status: ParityStatus
    output_parity_status: ParityStatus
    trace_parity_status: ParityStatus
    summary: Mapping[str, FrozenJson] = field(default_factory=dict)
    error: Mapping[str, FrozenJson] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_key(self.stage_key, field="stage_key")
        require_key(self.attempt_key, field="attempt_key")
        _require_aware(self.decision_cutoff_at, field="decision_cutoff_at")
        if self.decision_cutoff_at.date() != self.trade_date:
            raise ValueError("decision_cutoff_at must belong to trade_date")
        if not self.stage_status.strip() or not self.data_quality.strip():
            raise ValueError("stage_status and data_quality must not be empty")
        _require_optional_hashes(
            typed_input_fingerprint=self.typed_input_fingerprint,
            rule_output_fingerprint=self.rule_output_fingerprint,
            clause_trace_fingerprint=self.clause_trace_fingerprint,
        )
        _require_parity(self.input_parity_status, field="input_parity_status")
        _require_parity(self.output_parity_status, field="output_parity_status")
        _require_parity(self.trace_parity_status, field="trace_parity_status")
        object.__setattr__(self, "summary", _freeze_object(self.summary, field="summary"))
        object.__setattr__(self, "error", _freeze_object(self.error, field="error"))


@dataclass(frozen=True)
class ReplayInputFact:
    trade_date: date
    stage_key: str
    attempt_key: str
    input_key: str
    input_type: Literal["dataset", "stage_output"]
    semantic_role: str
    conformance_status: str
    content_fingerprint: str
    semantic_fingerprint: str
    parity_status: ParityStatus
    dataset_key: str | None = None
    upstream_stage_key: str | None = None
    upstream_attempt_key: str | None = None
    query_intent: Mapping[str, FrozenJson] = field(default_factory=dict)
    resolved_sources: tuple[FrozenJson, ...] = ()
    content_evidence: Mapping[str, FrozenJson] = field(default_factory=dict)
    conformance_reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for field_name in ("stage_key", "attempt_key", "input_key"):
            require_key(getattr(self, field_name), field=field_name)
        if self.input_type == "dataset":
            if self.dataset_key is None or self.upstream_stage_key or self.upstream_attempt_key:
                raise ValueError("dataset input requires only dataset_key identity")
            require_key(self.dataset_key, field="dataset_key")
        elif self.input_type == "stage_output":
            if self.dataset_key is not None or not (
                self.upstream_stage_key and self.upstream_attempt_key
            ):
                raise ValueError("stage_output input requires upstream stage/attempt identity")
            require_key(self.upstream_stage_key, field="upstream_stage_key")
            require_key(self.upstream_attempt_key, field="upstream_attempt_key")
        else:
            raise ValueError(f"unsupported input_type: {self.input_type}")
        require_sha256(self.content_fingerprint, field="content_fingerprint")
        require_sha256(self.semantic_fingerprint, field="semantic_fingerprint")
        _require_parity(self.parity_status, field="parity_status")
        object.__setattr__(
            self, "query_intent", _freeze_object(self.query_intent, field="query_intent")
        )
        object.__setattr__(
            self,
            "content_evidence",
            _freeze_object(self.content_evidence, field="content_evidence"),
        )
        frozen_sources = freeze_json(self.resolved_sources, path="resolved_sources")
        if not isinstance(frozen_sources, tuple):
            raise TypeError("resolved_sources must be an array")
        object.__setattr__(self, "resolved_sources", frozen_sources)
        object.__setattr__(self, "conformance_reasons", tuple(self.conformance_reasons))


@dataclass(frozen=True)
class SubjectOutcomeFact:
    trade_date: date
    subject_type: str
    subject_key: str
    outcome_key: str
    horizon: str
    target_trade_date: date | None
    maturity_status: MaturityStatus
    value_type: Literal["number", "boolean", "text"]
    executable: bool
    data_quality: str
    computation_mode: ComputationMode
    value_number: float | None = None
    value_boolean: bool | None = None
    value_text: str | None = None
    subject_role: str | None = None
    reference_value: float | None = None
    quality_reasons: tuple[str, ...] = ()
    source_identity: Mapping[str, FrozenJson] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_key(self.subject_type, field="subject_type")
        if not self.subject_key.strip():
            raise ValueError("subject_key must not be empty")
        require_key(self.outcome_key, field="outcome_key")
        if not self.horizon.strip() or not self.data_quality.strip():
            raise ValueError("horizon and data_quality must not be empty")
        if self.maturity_status not in {"pending", "mature", "invalid", "unavailable"}:
            raise ValueError(f"unsupported maturity_status: {self.maturity_status}")
        if self.computation_mode not in {"initial", "recomputed"}:
            raise ValueError(f"unsupported computation_mode: {self.computation_mode}")
        values = {
            "number": self.value_number,
            "boolean": self.value_boolean,
            "text": self.value_text,
        }
        if self.value_type not in values:
            raise ValueError(f"unsupported value_type: {self.value_type}")
        non_null = [key for key, value in values.items() if value is not None]
        if self.maturity_status == "mature" and non_null != [self.value_type]:
            raise ValueError("mature outcome requires exactly one value matching value_type")
        if self.maturity_status != "mature" and non_null:
            raise ValueError("non-mature outcome must not contain a value")
        for field_name in ("value_number", "reference_value"):
            value = getattr(self, field_name)
            if value is not None and not math.isfinite(value):
                raise ValueError(f"{field_name} must be finite")
        object.__setattr__(self, "quality_reasons", tuple(self.quality_reasons))
        object.__setattr__(
            self,
            "source_identity",
            _freeze_object(self.source_identity, field="source_identity"),
        )


@dataclass(frozen=True)
class ClauseObservationFact:
    trade_date: date
    stage_key: str
    attempt_key: str
    clause_key: str
    clause_version: str
    subject_type: str
    subject_key: str
    evaluation_status: str
    data_quality: str
    trace_fingerprint: str
    reason_codes: tuple[str, ...] = ()
    inputs: Mapping[str, FrozenJson] = field(default_factory=dict)
    output: Mapping[str, FrozenJson] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for field_name in ("stage_key", "attempt_key", "clause_key", "subject_type"):
            require_key(getattr(self, field_name), field=field_name)
        require_version(self.clause_version, field="clause_version")
        if not self.subject_key.strip():
            raise ValueError("subject_key must not be empty")
        if not self.evaluation_status.strip() or not self.data_quality.strip():
            raise ValueError("evaluation_status and data_quality must not be empty")
        require_sha256(self.trace_fingerprint, field="trace_fingerprint")
        object.__setattr__(self, "reason_codes", tuple(self.reason_codes))
        object.__setattr__(self, "inputs", _freeze_object(self.inputs, field="inputs"))
        object.__setattr__(self, "output", _freeze_object(self.output, field="output"))


@dataclass(frozen=True)
class DistributionFact:
    window_start_trade_date: date
    window_end_trade_date: date
    evidence_cohort: EvidenceCohort
    group_key: str
    outcome_key: str
    horizon: str
    subject_count: int
    trade_day_count: int
    statistics_status: StatisticsStatus
    source_fingerprint: str
    statistics: Mapping[str, FrozenJson]
    group_dimensions: Mapping[str, FrozenJson] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.window_start_trade_date > self.window_end_trade_date:
            raise ValueError("window start must not be after end")
        require_key(self.group_key, field="group_key")
        require_key(self.outcome_key, field="outcome_key")
        _require_non_negative(
            subject_count=self.subject_count,
            trade_day_count=self.trade_day_count,
        )
        _require_statistics(self.statistics_status)
        require_sha256(self.source_fingerprint, field="source_fingerprint")
        object.__setattr__(
            self, "statistics", _freeze_object(self.statistics, field="statistics")
        )
        object.__setattr__(
            self,
            "group_dimensions",
            _freeze_object(self.group_dimensions, field="group_dimensions"),
        )


@dataclass(frozen=True)
class HealthWindowFact:
    window_end_trade_date: date
    window_size_trading_days: int
    actual_trade_day_count: int
    evidence_cohort: EvidenceCohort
    group_key: str
    outcome_key: str
    horizon: str
    statistics_status: StatisticsStatus
    source_fingerprint: str
    metrics: Mapping[str, FrozenJson]

    def __post_init__(self) -> None:
        if self.window_size_trading_days <= 0:
            raise ValueError("window_size_trading_days must be positive")
        _require_non_negative(actual_trade_day_count=self.actual_trade_day_count)
        if self.actual_trade_day_count > self.window_size_trading_days:
            raise ValueError("actual_trade_day_count cannot exceed window size")
        require_key(self.group_key, field="group_key")
        require_key(self.outcome_key, field="outcome_key")
        _require_statistics(self.statistics_status)
        require_sha256(self.source_fingerprint, field="source_fingerprint")
        object.__setattr__(self, "metrics", _freeze_object(self.metrics, field="metrics"))


@dataclass(frozen=True)
class VersionComparisonFact:
    baseline_rule_key: str
    baseline_rule_version: str
    baseline_rule_definition_hash: str
    comparison_rule_key: str
    comparison_rule_version: str
    comparison_rule_definition_hash: str
    window_start_trade_date: date
    window_end_trade_date: date
    group_key: str
    outcome_key: str
    horizon: str
    paired_day_count: int
    statistics_status: StatisticsStatus
    source_fingerprint: str
    metrics: Mapping[str, FrozenJson]

    def __post_init__(self) -> None:
        require_key(self.baseline_rule_key, field="baseline_rule_key")
        require_version(self.baseline_rule_version, field="baseline_rule_version")
        require_sha256(
            self.baseline_rule_definition_hash,
            field="baseline_rule_definition_hash",
        )
        require_key(self.comparison_rule_key, field="comparison_rule_key")
        require_version(self.comparison_rule_version, field="comparison_rule_version")
        require_sha256(
            self.comparison_rule_definition_hash,
            field="comparison_rule_definition_hash",
        )
        if (
            self.baseline_rule_key,
            self.baseline_rule_version,
        ) == (self.comparison_rule_key, self.comparison_rule_version):
            raise ValueError("comparison rule identity must differ from baseline")
        if self.window_start_trade_date > self.window_end_trade_date:
            raise ValueError("window start must not be after end")
        require_key(self.group_key, field="group_key")
        require_key(self.outcome_key, field="outcome_key")
        _require_non_negative(paired_day_count=self.paired_day_count)
        _require_statistics(self.statistics_status)
        require_sha256(self.source_fingerprint, field="source_fingerprint")
        object.__setattr__(self, "metrics", _freeze_object(self.metrics, field="metrics"))


def _freeze_object(value: Mapping[str, object], *, field: str) -> Mapping[str, FrozenJson]:
    frozen = freeze_json(value, path=field)
    if not isinstance(frozen, Mapping):
        raise TypeError(f"{field} must be an object")
    return frozen


def _require_aware(value: datetime, *, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")


def _require_non_negative(**values: int) -> None:
    for field, value in values.items():
        if value < 0:
            raise ValueError(f"{field} must not be negative")


def _require_optional_hashes(**values: str | None) -> None:
    for field, value in values.items():
        if value is not None:
            require_sha256(value, field=field)


def _require_parity(value: str, *, field: str) -> None:
    if value not in {"exact", "mismatch", "unavailable", "not_applicable"}:
        raise ValueError(f"unsupported {field}: {value}")


def _require_statistics(value: str) -> None:
    if value not in {"available", "insufficient_sample"}:
        raise ValueError(f"unsupported statistics_status: {value}")
