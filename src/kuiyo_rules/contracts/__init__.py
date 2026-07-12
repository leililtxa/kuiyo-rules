"""Typed rule input and output contracts."""

from kuiyo_rules.contracts.opening_candidate import (
    CandidateEvaluationInput,
    CandidateEvaluationOutput,
    CandidateTierInput,
    CandidateTierOutput,
    OpeningCandidateGenerateInput,
    OpeningCandidateGenerateOutput,
)
from kuiyo_rules.contracts.opening_candidate_inputs import (
    build_evaluation_input,
    build_generate_input,
    build_tier_input,
    candidate_handoff_from_output,
    candidate_handoff_from_frame,
    canonical_candidate_handoff,
    canonical_evaluation_handoff,
    evaluation_handoff_from_output,
)

__all__ = [
    "CandidateEvaluationInput",
    "CandidateEvaluationOutput",
    "CandidateTierInput",
    "CandidateTierOutput",
    "OpeningCandidateGenerateInput",
    "OpeningCandidateGenerateOutput",
    "build_evaluation_input",
    "build_generate_input",
    "build_tier_input",
    "candidate_handoff_from_output",
    "candidate_handoff_from_frame",
    "canonical_candidate_handoff",
    "canonical_evaluation_handoff",
    "evaluation_handoff_from_output",
]
