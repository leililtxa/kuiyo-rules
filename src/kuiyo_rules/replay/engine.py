from __future__ import annotations

from collections.abc import Sequence
from typing import cast

from kuiyo_rules.evidence import (
    input_evidence_semantic_payload,
    semantic_fingerprint,
    typed_rule_contract_fingerprint,
)
from kuiyo_rules.registry import evaluate_rule, get_rule_version
from kuiyo_rules.replay.contracts import (
    ReplayDayResult,
    ReplayPlan,
    ReplayProgress,
    ReplayRequest,
    ReplayStatus,
    ReplayStageInputPlan,
    ReplayStageResult,
    ResolvedReplayStageData,
    RuleStageOutput,
)
from kuiyo_rules.replay.registry import ReplayPolicyRegistry


class ReplayInputError(RuntimeError):
    pass


class ReplayEvaluatorError(RuntimeError):
    pass


def build_replay_plan(
    request: ReplayRequest,
    *,
    registry: ReplayPolicyRegistry,
) -> ReplayPlan:
    version = get_rule_version(request.rule_key, request.rule_version)
    policy = registry.get(request.rule_key)
    return ReplayPlan(
        request.rule_key,
        request.rule_version,
        version.definition_hash,
        tuple(
            policy.build_day_plan(rule_version=version, trade_date=trade_date)
            for trade_date in request.trade_dates
        ),
    )


def prepare_next_stage(
    *,
    rule_key: str,
    rule_version: str,
    progress: ReplayProgress,
    registry: ReplayPolicyRegistry,
) -> tuple[ReplayProgress, ReplayStageInputPlan | None]:
    version = get_rule_version(rule_key, rule_version)
    policy = registry.get(rule_key)
    current = progress
    while current.next_attempt is not None and not policy.should_execute(
        attempt=current.next_attempt,
        progress=current,
    ):
        current = current.skip_next()
    if current.next_attempt is None:
        return current, None
    return current, policy.build_stage_input_plan(
        rule_version=version,
        progress=current,
    )


def execute_replay_stage(
    *,
    resolved: ResolvedReplayStageData,
    progress: ReplayProgress,
    registry: ReplayPolicyRegistry,
) -> ReplayStageResult:
    plan = resolved.plan
    if progress.next_attempt != plan.attempt:
        raise ValueError("resolved stage does not match replay progress")
    version = get_rule_version(plan.rule_key, plan.rule_version)
    policy = registry.get(plan.rule_key)
    try:
        rule_input, evidence = policy.build_rule_input(
            rule_version=version,
            resolved=resolved,
            progress=progress,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ReplayInputError(str(exc)) from exc
    try:
        output = cast(
            RuleStageOutput,
            evaluate_rule(
                rule_key=plan.rule_key,
                rule_version=plan.rule_version,
                stage_key=plan.attempt.stage_key,
                rule_input=rule_input,
            ),
        )
    except (KeyError, TypeError, ValueError, RuntimeError) as exc:
        raise ReplayEvaluatorError(str(exc)) from exc
    return ReplayStageResult(
        attempt=plan.attempt,
        status=output.status,
        data_quality=output.data_quality,
        rule_output=output,
        clause_traces=tuple(output.clause_traces),
        input_evidence=tuple(evidence),
        typed_input_fingerprint=typed_rule_contract_fingerprint(rule_input),
        rule_output_fingerprint=typed_rule_contract_fingerprint(output),
        clause_trace_fingerprint=semantic_fingerprint(tuple(output.clause_traces)),
    )


def finalize_replay_day(
    *,
    rule_key: str,
    rule_version: str,
    progress: ReplayProgress,
    errors: Sequence[str],
    registry: ReplayPolicyRegistry,
) -> ReplayDayResult:
    if not progress.is_complete and not errors:
        raise ValueError("cannot finalize an incomplete replay without an error")
    version = get_rule_version(rule_key, rule_version)
    status, quality = registry.get(rule_key).summarize_day(
        progress=progress,
        errors=errors,
    )
    status, quality = apply_input_conformance(
        status=status,
        quality=quality,
        stages=progress.completed_stages,
    )
    fingerprint = semantic_fingerprint(
        {
            "rule_key": rule_key,
            "rule_version": rule_version,
            "rule_definition_hash": version.definition_hash,
            "trade_date": progress.plan.trade_date,
            "plan": progress.plan,
            "stages": [
                {
                    "attempt": stage.attempt,
                    "status": stage.status,
                    "data_quality": stage.data_quality,
                    "rule_output": stage.rule_output,
                    "clause_traces": stage.clause_traces,
                    "inputs": [
                        input_evidence_semantic_payload(item)
                        for item in stage.input_evidence
                    ],
                }
                for stage in progress.completed_stages
            ],
        }
    )
    return ReplayDayResult(
        rule_key=rule_key,
        rule_version=rule_version,
        rule_definition_hash=version.definition_hash,
        trade_date=progress.plan.trade_date,
        stages=progress.completed_stages,
        status=cast(ReplayStatus, status),
        data_quality=quality,
        semantic_fingerprint=fingerprint,
        errors=tuple(errors),
    )


def apply_input_conformance(
    *,
    status: str,
    quality: str,
    stages: Sequence[ReplayStageResult],
) -> tuple[str, str]:
    decision_statuses = [
        evidence.conformance.status
        for stage in stages
        for evidence in stage.input_evidence
        if evidence.query.semantic_role == "decision"
    ]
    if "invalid" in decision_statuses:
        return "invalid_input", "missing"
    if "degraded" in decision_statuses and quality == "normal":
        return status, "degraded"
    return status, quality
