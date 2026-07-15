from __future__ import annotations

import math
from datetime import date

import pandas as pd
import pytest

from kuiyo_rules.audit import (
    AuditAsOf,
    AuditIdentity,
    AuditSpecification,
    OutcomeDefinition,
    OutcomePlan,
    ResolvedOutcomeBundle,
    ResolvedOutcomeInput,
    SubjectOutcomeFact,
    VersionComparisonFact,
    validate_audit_inputs,
)
from kuiyo_rules.evidence import ContentEvidence, QueryIntent
from kuiyo_rules.replay import ReplayDayResult, ReplayResult


RULE_HASH = "a" * 64
SPEC_HASH = "b" * 64
CONTENT_HASH = "c" * 64


def identity() -> AuditIdentity:
    return AuditIdentity(
        "opening_candidate_watch",
        "v001",
        RULE_HASH,
        "AUDIT-001",
        "v001",
        SPEC_HASH,
    )


def test_audit_specification_has_stable_definition_hash() -> None:
    specification = AuditSpecification(
        audit_spec_key="AUDIT-001",
        audit_spec_version="v001",
        target_rule_key="opening_candidate_watch",
        supported_rule_versions=("v001",),
        outcome_definitions=(
            OutcomeDefinition("t1_open", "T+1", "candidate_reference_price", "number", True),
        ),
        group_dimensions=("evidence_cohort",),
    )

    assert len(specification.definition_hash) == 64
    assert specification.definition_hash == specification.definition_hash


def test_audit_specification_rejects_noncanonical_identity() -> None:
    with pytest.raises(ValueError, match="AUDIT"):
        AuditSpecification(
            audit_spec_key="opening-candidate-audit",
            audit_spec_version="v001",
            target_rule_key="opening_candidate_watch",
            supported_rule_versions=("v001",),
            outcome_definitions=(
                OutcomeDefinition(
                    "t1_open", "T+1", "candidate_reference_price", "number", True
                ),
            ),
            group_dimensions=("evidence_cohort",),
        )


def test_mature_subject_outcome_requires_exactly_one_typed_value() -> None:
    with pytest.raises(ValueError, match="exactly one"):
        SubjectOutcomeFact(
            trade_date=date(2026, 7, 14),
            subject_type="stock_candidate",
            subject_key="600573.SH",
            outcome_key="t1_open",
            horizon="T+1",
            target_trade_date=date(2026, 7, 15),
            maturity_status="mature",
            value_type="number",
            executable=True,
            data_quality="normal",
            computation_mode="initial",
        )


def test_pending_subject_outcome_cannot_contain_value() -> None:
    with pytest.raises(ValueError, match="must not contain"):
        SubjectOutcomeFact(
            trade_date=date(2026, 7, 14),
            subject_type="stock_candidate",
            subject_key="600573.SH",
            outcome_key="t3_close",
            horizon="T+3",
            target_trade_date=date(2026, 7, 17),
            maturity_status="pending",
            value_type="number",
            executable=True,
            data_quality="normal",
            computation_mode="initial",
            value_number=0.05,
        )


def test_subject_outcome_rejects_nan() -> None:
    with pytest.raises(ValueError, match="finite"):
        SubjectOutcomeFact(
            trade_date=date(2026, 7, 14),
            subject_type="stock_candidate",
            subject_key="600573.SH",
            outcome_key="t1_open",
            horizon="T+1",
            target_trade_date=date(2026, 7, 15),
            maturity_status="mature",
            value_type="number",
            executable=True,
            data_quality="normal",
            computation_mode="initial",
            value_number=math.nan,
        )


def test_validate_audit_inputs_rejects_missing_resolved_requirement() -> None:
    audit_identity = identity()
    as_of = AuditAsOf(date(2026, 7, 15), date(2026, 7, 14))
    query = QueryIntent(
        input_key="outcome.daily",
        input_type="dataset",
        requested_range={"start": "2026-07-15", "end": "2026-07-15"},
        semantic_role="annotation",
        dataset_key="market.stock.quote.daily",
    )
    from kuiyo_rules.audit import OutcomeRequirement

    plan = OutcomePlan(
        audit_identity,
        as_of,
        (OutcomeRequirement("outcome.daily", date(2026, 7, 15), query),),
    )
    bundle = ResolvedOutcomeBundle(audit_identity, as_of, ())
    replay = ReplayResult(
        "opening_candidate_watch",
        "v001",
        RULE_HASH,
        (
            ReplayDayResult(
                "opening_candidate_watch",
                "v001",
                RULE_HASH,
                date(2026, 7, 14),
                (),
                "no_candidate",
                "normal",
                CONTENT_HASH,
            ),
        ),
        {},
    )

    with pytest.raises(ValueError, match="exactly match"):
        validate_audit_inputs(replay=replay, outcome_plan=plan, outcome_bundle=bundle)


def test_outcome_requirement_uses_query_input_key_as_single_identity() -> None:
    query = QueryIntent(
        input_key="outcome.daily",
        input_type="dataset",
        requested_range={"start": "2026-07-15", "end": "2026-07-15"},
        dataset_key="market.stock.quote.daily",
    )
    from kuiyo_rules.audit import OutcomeRequirement

    with pytest.raises(ValueError, match="must match"):
        OutcomeRequirement("another.key", date(2026, 7, 15), query)


def test_version_comparison_requires_both_definition_hashes() -> None:
    fact = VersionComparisonFact(
        baseline_rule_key="opening_candidate_watch",
        baseline_rule_version="v001",
        baseline_rule_definition_hash=RULE_HASH,
        comparison_rule_key="opening_candidate_watch",
        comparison_rule_version="v002",
        comparison_rule_definition_hash="d" * 64,
        window_start_trade_date=date(2026, 7, 14),
        window_end_trade_date=date(2026, 7, 15),
        group_key="all",
        outcome_key="t1_open",
        horizon="T+1",
        paired_day_count=2,
        statistics_status="insufficient_sample",
        source_fingerprint=CONTENT_HASH,
        metrics={},
    )

    assert fact.baseline_rule_definition_hash == RULE_HASH
    assert fact.comparison_rule_definition_hash == "d" * 64


def test_resolved_outcome_input_accepts_dataframe_without_persisting_it() -> None:
    content = ContentEvidence(
        row_count=1,
        entity_count=1,
        observation_count=1,
        content_fingerprint=CONTENT_HASH,
        max_known_at="2026-07-15T15:00:00+08:00",
        quality="normal",
        quality_reasons=(),
    )
    resolved = ResolvedOutcomeInput(
        "outcome.daily",
        QueryIntent(
            input_key="outcome.daily",
            input_type="dataset",
            requested_range={},
            dataset_key="market.stock.quote.daily",
        ),
        pd.DataFrame([{"symbol": "600573.SH", "close_price": 10.0}]),
        (),
        content,
    )

    assert len(resolved.frame) == 1
