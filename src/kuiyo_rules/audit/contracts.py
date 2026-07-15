from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from kuiyo_rules.audit.facts import (
    AuditIdentity,
    ClauseObservationFact,
    DistributionFact,
    HealthWindowFact,
    ReplayDayFact,
    ReplayInputFact,
    ReplayStageFact,
    SubjectOutcomeFact,
    VersionComparisonFact,
)
from kuiyo_rules.evidence import ContentEvidence, QueryIntent, ResolvedSourceEvidence
from kuiyo_rules.identifiers import require_key
from kuiyo_rules.replay import ReplayResult
from kuiyo_rules.serialization import FrozenJson, freeze_json


@dataclass(frozen=True)
class AuditAsOf:
    as_of_date: date
    cohort_start_date: date

    def __post_init__(self) -> None:
        if self.cohort_start_date > self.as_of_date:
            raise ValueError("cohort_start_date must not be after as_of_date")


@dataclass(frozen=True)
class OutcomeRequirement:
    requirement_key: str
    trade_date: date
    query: QueryIntent
    symbols: tuple[str, ...] = ()
    allow_full_scan: bool = False

    def __post_init__(self) -> None:
        require_key(self.requirement_key, field="requirement_key")
        if self.query.input_type != "dataset":
            raise ValueError("outcome requirements must resolve Dataset input")
        if self.requirement_key != self.query.input_key:
            raise ValueError("requirement_key must match query input_key")
        symbols = tuple(dict.fromkeys(str(item) for item in self.symbols))
        if self.query.symbol_count != len(symbols):
            raise ValueError("query symbol_count must match outcome resolution symbols")
        object.__setattr__(self, "symbols", symbols)


@dataclass(frozen=True)
class OutcomePlan:
    identity: AuditIdentity
    as_of: AuditAsOf
    requirements: tuple[OutcomeRequirement, ...]

    def __post_init__(self) -> None:
        keys = [item.requirement_key for item in self.requirements]
        if len(set(keys)) != len(keys):
            raise ValueError("requirements must have unique requirement_key values")
        object.__setattr__(self, "requirements", tuple(self.requirements))


@dataclass(frozen=True)
class ResolvedOutcomeInput:
    requirement_key: str
    query: QueryIntent
    frame: pd.DataFrame
    resolved_sources: tuple[ResolvedSourceEvidence, ...]
    content_evidence: ContentEvidence

    def __post_init__(self) -> None:
        require_key(self.requirement_key, field="requirement_key")
        if self.query.input_type != "dataset":
            raise ValueError("resolved outcome input requires Dataset QueryIntent")
        if self.query.input_key != self.requirement_key:
            raise ValueError("resolved outcome query must match requirement_key")
        object.__setattr__(self, "resolved_sources", tuple(self.resolved_sources))


@dataclass(frozen=True)
class ResolvedOutcomeBundle:
    identity: AuditIdentity
    as_of: AuditAsOf
    inputs: tuple[ResolvedOutcomeInput, ...]

    def __post_init__(self) -> None:
        keys = [item.requirement_key for item in self.inputs]
        if len(set(keys)) != len(keys):
            raise ValueError("inputs must have unique requirement_key values")
        object.__setattr__(self, "inputs", tuple(self.inputs))


@dataclass(frozen=True)
class AuditSummary:
    identity: AuditIdentity
    as_of_date: date
    cohort_start_date: date
    requested_day_count: int
    computed_day_count: int
    pending_outcome_count: int
    invalid_day_count: int
    unavailable_outcome_count: int
    coverage_status: str
    summary: Mapping[str, FrozenJson] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.cohort_start_date > self.as_of_date:
            raise ValueError("cohort_start_date must not be after as_of_date")
        for field_name in (
            "requested_day_count",
            "computed_day_count",
            "pending_outcome_count",
            "invalid_day_count",
            "unavailable_outcome_count",
        ):
            if getattr(self, field_name) < 0:
                raise ValueError(f"{field_name} must not be negative")
        if self.computed_day_count > self.requested_day_count:
            raise ValueError("computed_day_count cannot exceed requested_day_count")
        if self.coverage_status not in {"complete", "maturing", "incomplete", "invalid"}:
            raise ValueError(f"unsupported coverage_status: {self.coverage_status}")
        frozen = freeze_json(self.summary, path="summary")
        if not isinstance(frozen, Mapping):
            raise TypeError("summary must be an object")
        object.__setattr__(self, "summary", frozen)


@dataclass(frozen=True)
class AuditResult:
    summary: AuditSummary
    replay_days: tuple[ReplayDayFact, ...]
    replay_stages: tuple[ReplayStageFact, ...]
    replay_inputs: tuple[ReplayInputFact, ...]
    subject_outcomes: tuple[SubjectOutcomeFact, ...]
    clause_observations: tuple[ClauseObservationFact, ...]
    distributions: tuple[DistributionFact, ...]
    health_windows: tuple[HealthWindowFact, ...]
    version_comparisons: tuple[VersionComparisonFact, ...] = ()

    def __post_init__(self) -> None:
        for field_name in (
            "replay_days",
            "replay_stages",
            "replay_inputs",
            "subject_outcomes",
            "clause_observations",
            "distributions",
            "health_windows",
            "version_comparisons",
        ):
            object.__setattr__(self, field_name, tuple(getattr(self, field_name)))


def validate_audit_inputs(
    *,
    replay: ReplayResult,
    outcome_plan: OutcomePlan,
    outcome_bundle: ResolvedOutcomeBundle,
) -> None:
    identity = outcome_plan.identity
    if outcome_bundle.identity != identity:
        raise ValueError("outcome bundle identity must match outcome plan")
    if outcome_bundle.as_of != outcome_plan.as_of:
        raise ValueError("outcome bundle as_of must match outcome plan")
    if (
        replay.rule_key,
        replay.rule_version,
        replay.rule_definition_hash,
    ) != (identity.rule_key, identity.rule_version, identity.rule_definition_hash):
        raise ValueError("replay identity must match audit identity")
    planned = {item.requirement_key for item in outcome_plan.requirements}
    resolved = {item.requirement_key for item in outcome_bundle.inputs}
    if planned != resolved:
        raise ValueError("resolved outcome inputs must exactly match planned requirements")
    plans = {item.requirement_key: item for item in outcome_plan.requirements}
    for item in outcome_bundle.inputs:
        expected = plans[item.requirement_key].query
        if (
            expected.dataset_key,
            expected.requested_range,
            expected.fields,
            expected.filters,
            expected.symbol_count,
            expected.symbol_set_fingerprint,
            expected.missing_policy,
        ) != (
            item.query.dataset_key,
            item.query.requested_range,
            item.query.fields,
            item.query.filters,
            item.query.symbol_count,
            item.query.symbol_set_fingerprint,
            item.query.missing_policy,
        ):
            raise ValueError("resolved outcome query does not match outcome plan")
