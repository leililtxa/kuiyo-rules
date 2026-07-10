from __future__ import annotations

from dataclasses import fields

from kuiyo_rules.contracts import (
    CandidateEvaluationInput,
    CandidateEvaluationOutput,
    CandidateTierInput,
    CandidateTierOutput,
    OpeningCandidateGenerateInput,
    OpeningCandidateGenerateOutput,
)


CONTRACT_TYPES = (
    OpeningCandidateGenerateInput,
    OpeningCandidateGenerateOutput,
    CandidateEvaluationInput,
    CandidateEvaluationOutput,
    CandidateTierInput,
    CandidateTierOutput,
)

FORBIDDEN_FIELDS = {
    "connection",
    "database_id",
    "generated_at",
    "job_run_id",
    "research_candidate_id",
    "research_candidate_set_id",
    "schedule_key",
}


def test_rule_contracts_do_not_expose_runtime_or_database_fields() -> None:
    for contract_type in CONTRACT_TYPES:
        field_names = {field.name for field in fields(contract_type)}
        assert field_names.isdisjoint(FORBIDDEN_FIELDS), contract_type.__name__

