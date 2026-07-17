from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from kuiyo_rules.audit.contracts import (
    AuditAsOf,
    AuditResult,
    OutcomePlan,
    ResolvedOutcomeBundle,
)
from kuiyo_rules.audit.parity import ProductionStageEvidence
from kuiyo_rules.audit.specifications import AuditSpecification
from kuiyo_rules.replay import ReplayResult


BuildOutcomePlan = Callable[[ReplayResult, AuditSpecification, AuditAsOf], OutcomePlan]
ComputeAudit = Callable[
    [
        ReplayResult,
        AuditSpecification,
        OutcomePlan,
        ResolvedOutcomeBundle,
        Sequence[ProductionStageEvidence],
    ],
    AuditResult,
]


@dataclass(frozen=True)
class RuleAuditPolicy:
    specification: AuditSpecification
    build_outcome_plan: BuildOutcomePlan
    compute: ComputeAudit


class AuditSpecificationRegistry:
    def __init__(self, specifications: Sequence[AuditSpecification]) -> None:
        mapping = {
            (item.audit_spec_key, item.audit_spec_version): item
            for item in specifications
        }
        if len(mapping) != len(specifications):
            raise ValueError("duplicate AuditSpecification identity")
        self._specifications: Mapping[tuple[str, str], AuditSpecification] = mapping

    def get(self, audit_spec_key: str, audit_spec_version: str) -> AuditSpecification:
        try:
            return self._specifications[(audit_spec_key, audit_spec_version)]
        except KeyError as exc:
            raise KeyError(
                f"unknown audit specification: {audit_spec_key}/{audit_spec_version}"
            ) from exc


class RuleAuditPolicyRegistry:
    def __init__(self, policies: Sequence[RuleAuditPolicy]) -> None:
        mapping = {
            (
                item.specification.audit_spec_key,
                item.specification.audit_spec_version,
            ): item
            for item in policies
        }
        if len(mapping) != len(policies):
            raise ValueError("duplicate RuleAuditPolicy identity")
        self._policies: Mapping[tuple[str, str], RuleAuditPolicy] = mapping

    def get(self, audit_spec_key: str, audit_spec_version: str) -> RuleAuditPolicy:
        try:
            return self._policies[(audit_spec_key, audit_spec_version)]
        except KeyError as exc:
            raise KeyError(
                f"unknown audit policy: {audit_spec_key}/{audit_spec_version}"
            ) from exc
