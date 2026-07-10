"""Pure rule contracts and deterministic evaluators for Kuiyo."""

from kuiyo_rules.clauses import RuleClauseReference
from kuiyo_rules.contracts import (
    CandidateEvaluationInput,
    CandidateEvaluationOutput,
    CandidateTierInput,
    CandidateTierOutput,
    OpeningCandidateGenerateInput,
    OpeningCandidateGenerateOutput,
)
from kuiyo_rules.definitions import ResearchRuleDefinition, ResearchRuleVersion
from kuiyo_rules.registry import RuleSpec, RuleStageSpec, get_rule_spec, get_rule_version

__all__ = [
    "CandidateEvaluationInput",
    "CandidateEvaluationOutput",
    "CandidateTierInput",
    "CandidateTierOutput",
    "OpeningCandidateGenerateInput",
    "OpeningCandidateGenerateOutput",
    "ResearchRuleDefinition",
    "ResearchRuleVersion",
    "RuleClauseReference",
    "RuleSpec",
    "RuleStageSpec",
    "get_rule_spec",
    "get_rule_version",
]
