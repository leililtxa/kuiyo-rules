from __future__ import annotations

from collections import Counter

from kuiyo_rules.contracts import CandidateEvaluationInput, CandidateEvaluationOutput
from kuiyo_rules.definitions import ResearchRuleVersion
from kuiyo_rules.evaluation.opening_candidate.evaluation_features import (
    build_execution_features,
)
from kuiyo_rules.evaluation.opening_candidate.evaluation_rules import (
    apply_execution_confirmation,
)
from kuiyo_rules.evaluation.opening_candidate.generate import rule_identity
from kuiyo_rules.evaluation.opening_candidate.parameters import evaluation_parameters
from kuiyo_rules.quality import frame_data_quality
from kuiyo_rules.evaluation.opening_candidate.traces import evaluation_clause_traces


def evaluate_opening_candidates(
    *,
    rule_version: ResearchRuleVersion,
    rule_input: CandidateEvaluationInput,
) -> CandidateEvaluationOutput:
    parameters = evaluation_parameters(rule_version)
    features = build_execution_features(
        candidates=rule_input.candidates,
        stock_quotes=rule_input.stock_quotes,
        candidate_industries=rule_input.candidate_industries,
        industry_members=rule_input.industry_members,
        industry_quotes=rule_input.industry_quotes,
        index_quotes=rule_input.index_quotes,
        candidate_cutoff_at=rule_input.candidate_cutoff_at,
        execution_cutoff_at=rule_input.evaluation_cutoff_at,
    )
    evaluations = apply_execution_confirmation(features, parameters=parameters)
    if evaluations.empty:
        return CandidateEvaluationOutput(
            status="missing_data",
            data_quality="missing",
            evaluations=evaluations,
            summary={
                "reason": "no_candidate_features",
                "rule": rule_identity(rule_version),
            },
            clause_traces=evaluation_clause_traces(
                rule_version=rule_version,
                cutoff_at=rule_input.evaluation_cutoff_at,
                evaluations=evaluations,
                status="missing_data",
                data_quality="missing",
            ),
        )
    counts = Counter(str(value) for value in evaluations["decision"])
    data_quality = frame_data_quality(evaluations)
    return CandidateEvaluationOutput(
        status="ok",
        data_quality=data_quality,
        evaluations=evaluations,
        summary={
            "candidate_count": int(len(rule_input.candidates)),
            "evaluation_count": int(len(evaluations)),
            "decision_counts": dict(counts),
            "stock_quote_row_count": int(len(rule_input.stock_quotes)),
            "industry_quote_row_count": int(len(rule_input.industry_quotes)),
            "index_quote_row_count": int(len(rule_input.index_quotes)),
            "rule": rule_identity(rule_version),
        },
        clause_traces=evaluation_clause_traces(
            rule_version=rule_version,
            cutoff_at=rule_input.evaluation_cutoff_at,
            evaluations=evaluations,
            status="ok",
            data_quality=data_quality,
        ),
    )
