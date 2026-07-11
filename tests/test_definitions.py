from __future__ import annotations

from dataclasses import replace

import pytest

from kuiyo_rules.clauses import RuleClauseReference
from kuiyo_rules.definitions import OPENING_CANDIDATE_BASELINE_V001, ResearchRuleVersion


BASELINE_HASH = "271439f66e997b3a1490204448b83532326a11510593689624d060d61ce8f9ff"


def test_opening_candidate_baseline_has_stable_definition_hash() -> None:
    assert OPENING_CANDIDATE_BASELINE_V001.definition_hash == BASELINE_HASH
    assert OPENING_CANDIDATE_BASELINE_V001.conformance_status == "conformant"
    assert OPENING_CANDIDATE_BASELINE_V001.evidence_status == "baseline_unverified"


def test_non_semantic_metadata_does_not_change_definition_hash() -> None:
    changed = replace(
        OPENING_CANDIDATE_BASELINE_V001,
        metadata={"note": "non-semantic review note"},
    )

    assert changed.definition_hash == BASELINE_HASH


def test_nested_rule_definition_values_are_immutable() -> None:
    with pytest.raises(TypeError):
        OPENING_CANDIDATE_BASELINE_V001.decision_policy["generate"] = {}  # type: ignore[index]


def test_rule_version_rejects_non_canonical_version() -> None:
    with pytest.raises(ValueError, match="rule_version"):
        replace(OPENING_CANDIDATE_BASELINE_V001, rule_version="v0.2")


def test_rule_version_rejects_nan_parameters() -> None:
    invalid_clause = RuleClauseReference(
        clause_key="opening.invalid",
        clause_version="v001",
        clause_type="invariant",
        source_refs=("test",),
        parameters={},
    )

    with pytest.raises(ValueError, match="NaN or infinity"):
        replace(
            OPENING_CANDIDATE_BASELINE_V001,
            clause_composition=(invalid_clause,),
            decision_policy={"value": float("nan")},
        )


def test_rule_version_is_a_pure_definition_without_database_identity() -> None:
    fields = set(ResearchRuleVersion.__dataclass_fields__)

    assert fields.isdisjoint(
        {
            "id",
            "job_run_id",
            "research_candidate_set_id",
            "schedule_key",
            "handler",
            "evaluator_key",
        }
    )
