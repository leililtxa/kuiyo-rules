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
]
