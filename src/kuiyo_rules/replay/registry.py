from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol

from kuiyo_rules.definitions import ResearchRuleVersion
from kuiyo_rules.replay.contracts import (
    ReplayDayPlan,
    ReplayProgress,
    ReplayStageAttempt,
    ReplayStageInputPlan,
    ResolvedReplayStageData,
    RuleStageOutput,
)


class RuleReplayPolicy(Protocol):
    rule_key: str

    def build_day_plan(
        self,
        *,
        rule_version: ResearchRuleVersion,
        trade_date,
    ) -> ReplayDayPlan: ...

    def should_execute(
        self,
        *,
        attempt: ReplayStageAttempt,
        progress: ReplayProgress,
    ) -> bool: ...

    def build_stage_input_plan(
        self,
        *,
        rule_version: ResearchRuleVersion,
        progress: ReplayProgress,
    ) -> ReplayStageInputPlan: ...

    def build_rule_input(
        self,
        *,
        rule_version: ResearchRuleVersion,
        resolved: ResolvedReplayStageData,
        progress: ReplayProgress,
    ) -> tuple[object, tuple]: ...

    def summarize_day(
        self,
        *,
        progress: ReplayProgress,
        errors: Sequence[str],
    ) -> tuple[str, str]: ...


class ReplayPolicyRegistry:
    def __init__(self, policies: Sequence[RuleReplayPolicy]) -> None:
        mapping = {policy.rule_key: policy for policy in policies}
        if len(mapping) != len(policies):
            raise ValueError("duplicate replay policy rule_key")
        self._policies: Mapping[str, RuleReplayPolicy] = mapping

    def get(self, rule_key: str) -> RuleReplayPolicy:
        try:
            return self._policies[rule_key]
        except KeyError as exc:
            raise KeyError(f"no replay policy registered for rule_key: {rule_key}") from exc

