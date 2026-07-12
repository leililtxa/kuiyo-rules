"""Pure rule contracts and deterministic evaluators for Kuiyo."""

from kuiyo_rules.clauses import ClauseTrace, RuleClauseReference
from kuiyo_rules.contracts import (
    CandidateEvaluationInput,
    CandidateEvaluationOutput,
    CandidateTierInput,
    CandidateTierOutput,
    OpeningCandidateGenerateInput,
    OpeningCandidateGenerateOutput,
)
from kuiyo_rules.definitions import ResearchRuleDefinition, ResearchRuleVersion
from kuiyo_rules.evaluation import (
    evaluate_opening_candidates,
    generate_opening_candidates,
    tier_opening_candidates,
)
from kuiyo_rules.evidence import (
    ContentEvidence,
    InputEvidence,
    KnownTimeConformance,
    QueryIntent,
    ResolvedSourceEvidence,
    dataframe_fingerprint,
    semantic_fingerprint,
    typed_rule_contract_fingerprint,
)
from kuiyo_rules.registry import (
    RuleSpec,
    RuleStageSpec,
    evaluate_rule,
    get_rule_spec,
    get_rule_version,
)

__all__ = [
    "CandidateEvaluationInput",
    "CandidateEvaluationOutput",
    "CandidateTierInput",
    "CandidateTierOutput",
    "ClauseTrace",
    "ContentEvidence",
    "InputEvidence",
    "KnownTimeConformance",
    "OpeningCandidateGenerateInput",
    "OpeningCandidateGenerateOutput",
    "QueryIntent",
    "ResolvedSourceEvidence",
    "ResearchRuleDefinition",
    "ResearchRuleVersion",
    "RuleClauseReference",
    "RuleSpec",
    "RuleStageSpec",
    "evaluate_opening_candidates",
    "evaluate_rule",
    "get_rule_spec",
    "get_rule_version",
    "generate_opening_candidates",
    "dataframe_fingerprint",
    "semantic_fingerprint",
    "tier_opening_candidates",
    "typed_rule_contract_fingerprint",
]
