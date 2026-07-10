from __future__ import annotations

import pytest

from kuiyo_rules import (
    CandidateEvaluationInput,
    CandidateEvaluationOutput,
    CandidateTierInput,
    CandidateTierOutput,
    OpeningCandidateGenerateInput,
    OpeningCandidateGenerateOutput,
    evaluate_rule,
    get_rule_spec,
    get_rule_version,
)


def test_opening_candidate_registry_exposes_all_stage_contracts() -> None:
    spec = get_rule_spec("opening_candidate_watch")

    assert spec.stages["generate"].input_type is OpeningCandidateGenerateInput
    assert spec.stages["generate"].output_type is OpeningCandidateGenerateOutput
    assert spec.stages["evaluate"].input_type is CandidateEvaluationInput
    assert spec.stages["evaluate"].output_type is CandidateEvaluationOutput
    assert spec.stages["tier"].input_type is CandidateTierInput
    assert spec.stages["tier"].output_type is CandidateTierOutput
    assert all(callable(stage.evaluator) for stage in spec.stages.values())


def test_registry_resolves_immutable_baseline_version() -> None:
    version = get_rule_version("opening_candidate_watch", "v001")

    assert version.rule_key == "opening_candidate_watch"
    assert version.metadata["legacy_rule_version"] == "v0.2"


def test_registry_rejects_unknown_rule_or_version() -> None:
    with pytest.raises(KeyError, match="unknown rule_key"):
        get_rule_spec("unknown")
    with pytest.raises(KeyError, match="unknown rule version"):
        get_rule_version("opening_candidate_watch", "v999")


def test_registry_rejects_wrong_stage_input_type() -> None:
    with pytest.raises(TypeError, match="invalid input"):
        evaluate_rule(
            rule_key="opening_candidate_watch",
            rule_version="v001",
            stage_key="generate",
            rule_input=object(),
        )
