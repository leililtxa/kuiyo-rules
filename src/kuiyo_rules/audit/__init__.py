"""Pure audit specifications, plans, and typed facts."""

from kuiyo_rules.audit.contracts import (
    AuditAsOf,
    AuditResult,
    AuditSummary,
    OutcomePlan,
    OutcomeRequirement,
    ResolvedOutcomeBundle,
    ResolvedOutcomeInput,
    validate_audit_inputs,
)
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
from kuiyo_rules.audit.specifications import AuditSpecification, OutcomeDefinition
from kuiyo_rules.audit.opening_candidate import (
    OPENING_CANDIDATE_AUDIT_V001,
    build_opening_candidate_outcome_plan,
    compute_opening_candidate_audit,
)
from kuiyo_rules.audit.statistics import (
    cluster_bootstrap_interval,
    compare_rule_versions,
    summarize_outcomes,
)
from kuiyo_rules.audit.parity import (
    ProductionInputEvidence,
    ProductionReplayParity,
    ProductionStageEvidence,
    StageParity,
    aggregate_parity,
    compare_production_replay,
)
from kuiyo_rules.audit.registry import (
    AuditSpecificationRegistry,
    RuleAuditPolicy,
    RuleAuditPolicyRegistry,
)

__all__ = [
    "AuditAsOf",
    "AuditIdentity",
    "AuditResult",
    "AuditSpecification",
    "AuditSummary",
    "ClauseObservationFact",
    "DistributionFact",
    "HealthWindowFact",
    "OutcomeDefinition",
    "OutcomePlan",
    "OutcomeRequirement",
    "ReplayDayFact",
    "ReplayInputFact",
    "ReplayStageFact",
    "ResolvedOutcomeBundle",
    "ResolvedOutcomeInput",
    "SubjectOutcomeFact",
    "VersionComparisonFact",
    "validate_audit_inputs",
    "OPENING_CANDIDATE_AUDIT_V001",
    "build_opening_candidate_outcome_plan",
    "compute_opening_candidate_audit",
    "cluster_bootstrap_interval",
    "compare_rule_versions",
    "summarize_outcomes",
    "ProductionInputEvidence",
    "ProductionReplayParity",
    "ProductionStageEvidence",
    "StageParity",
    "aggregate_parity",
    "compare_production_replay",
    "AuditSpecificationRegistry",
    "DEFAULT_AUDIT_SPECIFICATIONS",
    "get_audit_specification",
    "RuleAuditPolicy",
    "RuleAuditPolicyRegistry",
    "DEFAULT_AUDIT_POLICIES",
    "get_audit_policy",
]

DEFAULT_AUDIT_SPECIFICATIONS = AuditSpecificationRegistry(
    (OPENING_CANDIDATE_AUDIT_V001,)
)


def get_audit_specification(
    audit_spec_key: str,
    audit_spec_version: str,
) -> AuditSpecification:
    return DEFAULT_AUDIT_SPECIFICATIONS.get(audit_spec_key, audit_spec_version)


def _build_opening_candidate_plan(replay, specification, as_of):
    return build_opening_candidate_outcome_plan(
        replay=replay,
        specification=specification,
        as_of=as_of,
    )


def _compute_opening_candidate(
    replay,
    specification,
    outcome_plan,
    outcome_bundle,
    production_evidence,
):
    return compute_opening_candidate_audit(
        replay=replay,
        specification=specification,
        outcome_plan=outcome_plan,
        outcome_bundle=outcome_bundle,
        production_evidence=production_evidence,
    )


DEFAULT_AUDIT_POLICIES = RuleAuditPolicyRegistry(
    (
        RuleAuditPolicy(
            OPENING_CANDIDATE_AUDIT_V001,
            _build_opening_candidate_plan,
            _compute_opening_candidate,
        ),
    )
)


def get_audit_policy(audit_spec_key: str, audit_spec_version: str) -> RuleAuditPolicy:
    return DEFAULT_AUDIT_POLICIES.get(audit_spec_key, audit_spec_version)
