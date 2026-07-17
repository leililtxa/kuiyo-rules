from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date

from kuiyo_rules.audit.facts import ParityStatus
from kuiyo_rules.identifiers import require_key, require_sha256, require_version
from kuiyo_rules.replay import ReplayDayResult, ReplayStageResult
from kuiyo_rules.serialization import FrozenJson, freeze_json


@dataclass(frozen=True)
class ProductionInputEvidence:
    input_key: str
    content_fingerprint: str
    semantic_fingerprint: str

    def __post_init__(self) -> None:
        require_key(self.input_key, field="input_key")
        require_sha256(self.content_fingerprint, field="content_fingerprint")
        require_sha256(self.semantic_fingerprint, field="semantic_fingerprint")


@dataclass(frozen=True)
class ProductionStageEvidence:
    rule_key: str
    rule_version: str
    rule_definition_hash: str
    trade_date: date
    stage_key: str
    attempt_key: str
    typed_input_fingerprint: str | None
    rule_output_fingerprint: str | None
    clause_trace_fingerprint: str | None
    inputs: tuple[ProductionInputEvidence, ...] = ()
    metadata: Mapping[str, FrozenJson] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_key(self.rule_key, field="rule_key")
        require_version(self.rule_version, field="rule_version")
        require_sha256(self.rule_definition_hash, field="rule_definition_hash")
        require_key(self.stage_key, field="stage_key")
        require_key(self.attempt_key, field="attempt_key")
        for field_name in (
            "typed_input_fingerprint",
            "rule_output_fingerprint",
            "clause_trace_fingerprint",
        ):
            value = getattr(self, field_name)
            if value is not None:
                require_sha256(value, field=field_name)
        inputs = tuple(self.inputs)
        if len({item.input_key for item in inputs}) != len(inputs):
            raise ValueError("production stage inputs must have unique input_key values")
        metadata = freeze_json(self.metadata, path="metadata")
        if not isinstance(metadata, Mapping):
            raise TypeError("metadata must be an object")
        object.__setattr__(self, "inputs", inputs)
        object.__setattr__(self, "metadata", metadata)


@dataclass(frozen=True)
class StageParity:
    input_status: ParityStatus
    output_status: ParityStatus
    trace_status: ParityStatus
    input_statuses: Mapping[str, ParityStatus] = field(default_factory=dict)
    reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        statuses = dict(self.input_statuses)
        if any(value not in _PARITY_STATUSES for value in statuses.values()):
            raise ValueError("unsupported input parity status")
        object.__setattr__(self, "input_statuses", statuses)
        object.__setattr__(self, "reasons", tuple(self.reasons))


@dataclass(frozen=True)
class ProductionReplayParity:
    stages: Mapping[tuple[date, str, str], StageParity]

    def stage(
        self,
        trade_date: date,
        stage_key: str,
        attempt_key: str,
    ) -> StageParity | None:
        return self.stages.get((trade_date, stage_key, attempt_key))

    def day_stage_status(self, trade_date: date) -> ParityStatus:
        values = [
            item
            for (day, _stage, _attempt), parity in self.stages.items()
            if day == trade_date
            for item in (parity.input_status, parity.output_status, parity.trace_status)
        ]
        return aggregate_parity(values)

    def day_input_status(self, trade_date: date) -> ParityStatus:
        values = [
            status
            for (day, _stage, _attempt), parity in self.stages.items()
            if day == trade_date
            for status in parity.input_statuses.values()
        ]
        return aggregate_parity(values)


_PARITY_STATUSES = {"exact", "mismatch", "unavailable", "not_applicable"}


def compare_production_replay(
    production: Sequence[ProductionStageEvidence],
    replay_days: Sequence[ReplayDayResult],
) -> ProductionReplayParity:
    replay_stages = {
        _stage_identity(day, stage): (day, stage)
        for day in replay_days
        for stage in day.stages
    }
    production_stages = {
        (item.trade_date, item.stage_key, item.attempt_key): item
        for item in production
    }
    if len(production_stages) != len(production):
        raise ValueError("production evidence must have unique stage identity")

    parity: dict[tuple[date, str, str], StageParity] = {}
    for identity, (day, stage) in replay_stages.items():
        candidate = production_stages.get(identity)
        if candidate is None:
            candidate = _single_stage_candidate(
                production,
                trade_date=day.trade_date,
                stage_key=stage.attempt.stage_key,
            )
        parity[identity] = compare_stage(candidate, day, stage)
    return ProductionReplayParity(parity)


def compare_stage(
    production: ProductionStageEvidence | None,
    replay_day: ReplayDayResult,
    replay_stage: ReplayStageResult,
) -> StageParity:
    if production is None:
        return StageParity(
            "unavailable",
            "unavailable",
            "unavailable",
            {
                item.query.input_key: "unavailable"
                for item in replay_stage.input_evidence
            },
            ("production_stage_missing",),
        )
    if (
        production.rule_key,
        production.rule_version,
        production.trade_date,
        production.stage_key,
    ) != (
        replay_day.rule_key,
        replay_day.rule_version,
        replay_day.trade_date,
        replay_stage.attempt.stage_key,
    ):
        raise ValueError("production evidence does not match replay stage identity")

    reasons: list[str] = []
    definition_matches = production.rule_definition_hash == replay_day.rule_definition_hash
    attempt_matches = production.attempt_key == replay_stage.attempt.attempt_key
    if not definition_matches:
        reasons.append("rule_definition_hash_mismatch")
    if not attempt_matches:
        reasons.append("attempt_key_mismatch")
    comparable = definition_matches and attempt_matches
    input_status = compare_fingerprint(
        production.typed_input_fingerprint,
        replay_stage.typed_input_fingerprint,
        comparable=comparable,
    )
    output_status = compare_fingerprint(
        production.rule_output_fingerprint,
        replay_stage.rule_output_fingerprint,
        comparable=comparable,
    )
    trace_status = compare_fingerprint(
        production.clause_trace_fingerprint,
        replay_stage.clause_trace_fingerprint,
        comparable=comparable,
    )
    production_inputs = {item.input_key: item for item in production.inputs}
    replay_inputs = {
        item.query.input_key: item
        for item in replay_stage.input_evidence
    }
    input_statuses: dict[str, ParityStatus] = {}
    for input_key in sorted(set(production_inputs) | set(replay_inputs)):
        left = production_inputs.get(input_key)
        right = replay_inputs.get(input_key)
        input_statuses[input_key] = compare_fingerprint(
            None if left is None else left.semantic_fingerprint,
            None if right is None else _replay_input_semantic_fingerprint(right),
            comparable=comparable,
        )
    return StageParity(
        input_status,
        output_status,
        trace_status,
        input_statuses,
        tuple(reasons),
    )


def compare_fingerprint(
    left: str | None,
    right: str | None,
    *,
    comparable: bool = True,
) -> ParityStatus:
    if not comparable or left is None or right is None:
        return "unavailable"
    return "exact" if left == right else "mismatch"


def aggregate_parity(values: Sequence[ParityStatus]) -> ParityStatus:
    statuses = tuple(values)
    if not statuses:
        return "not_applicable"
    if "mismatch" in statuses:
        return "mismatch"
    if "unavailable" in statuses:
        return "unavailable"
    if all(item == "not_applicable" for item in statuses):
        return "not_applicable"
    return "exact"


def _single_stage_candidate(
    production: Sequence[ProductionStageEvidence],
    *,
    trade_date: date,
    stage_key: str,
) -> ProductionStageEvidence | None:
    candidates = [
        item
        for item in production
        if item.trade_date == trade_date and item.stage_key == stage_key
    ]
    return candidates[0] if len(candidates) == 1 else None


def _stage_identity(
    day: ReplayDayResult,
    stage: ReplayStageResult,
) -> tuple[date, str, str]:
    return day.trade_date, stage.attempt.stage_key, stage.attempt.attempt_key


def _replay_input_semantic_fingerprint(evidence) -> str:
    from kuiyo_rules.evidence import input_evidence_semantic_fingerprint

    return input_evidence_semantic_fingerprint(evidence)
