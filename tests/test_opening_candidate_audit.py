from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from kuiyo_rules import OpeningCandidateGenerateOutput, get_rule_version
from kuiyo_rules.audit import (
    OPENING_CANDIDATE_AUDIT_V001,
    AuditAsOf,
    ResolvedOutcomeBundle,
    ResolvedOutcomeInput,
    build_opening_candidate_outcome_plan,
    compute_opening_candidate_audit,
    get_audit_specification,
    ProductionStageEvidence,
)
from kuiyo_rules.evidence import ContentEvidence
from kuiyo_rules.replay import ReplayDayResult, ReplayResult, ReplayStageAttempt, ReplayStageResult


TZ = ZoneInfo("Asia/Shanghai")


def test_opening_candidate_audit_plans_external_outcome_datasets() -> None:
    replay = replay_result(candidate=True)
    as_of = AuditAsOf(date(2026, 7, 15), date(2026, 7, 14))

    plan = build_opening_candidate_outcome_plan(
        replay=replay,
        specification=OPENING_CANDIDATE_AUDIT_V001,
        as_of=as_of,
    )

    assert [item.query.dataset_key for item in plan.requirements] == [
        "market.calendar.trading_calendar.daily",
        "market.stock.quote.daily",
        "market.stock.quote.window",
        "market.stock.quote.minute",
    ]
    assert plan.requirements[1].symbols == ("600001.SH",)


def test_audit_specification_registry_resolves_canonical_identity() -> None:
    assert (
        get_audit_specification("AUDIT-001", "v001")
        is OPENING_CANDIDATE_AUDIT_V001
    )


def test_opening_candidate_audit_returns_typed_mature_and_pending_facts() -> None:
    replay = replay_result(candidate=True)
    as_of = AuditAsOf(date(2026, 7, 15), date(2026, 7, 14))
    plan = build_opening_candidate_outcome_plan(
        replay=replay,
        specification=OPENING_CANDIDATE_AUDIT_V001,
        as_of=as_of,
    )
    frames = {
        "outcome.calendar": pd.DataFrame(
            [
                {"calendar_date": date(2026, 7, 14), "is_trading_day": True},
                {"calendar_date": date(2026, 7, 15), "is_trading_day": True},
                {"calendar_date": date(2026, 7, 16), "is_trading_day": True},
                {"calendar_date": date(2026, 7, 17), "is_trading_day": True},
                {"calendar_date": date(2026, 7, 20), "is_trading_day": True},
                {"calendar_date": date(2026, 7, 21), "is_trading_day": True},
            ]
        ),
        "outcome.stock_daily": pd.DataFrame(
            [
                {
                    "trade_date": date(2026, 7, 14),
                    "symbol": "600001.SH",
                    "open_price": 10.0,
                    "close_price": 10.5,
                    "up_limit_price": 11.0,
                    "down_limit_price": 9.0,
                },
                {
                    "trade_date": date(2026, 7, 15),
                    "symbol": "600001.SH",
                    "open_price": 10.6,
                    "close_price": 10.8,
                    "up_limit_price": 11.55,
                    "down_limit_price": 9.45,
                },
            ]
        ),
        "outcome.stock_window": pd.DataFrame(
            [
                {
                    "trade_date": date(2026, 7, 14),
                    "snapshot_at": datetime(2026, 7, 14, 10, 0, tzinfo=TZ),
                    "symbol": "600001.SH",
                    "last_price": 10.7,
                }
            ]
        ),
        "outcome.stock_minute": pd.DataFrame(),
    }
    bundle = ResolvedOutcomeBundle(
        plan.identity,
        as_of,
        tuple(
            ResolvedOutcomeInput(
                item.requirement_key,
                item.query,
                frames[item.requirement_key],
                (),
                content(item.requirement_key),
            )
            for item in plan.requirements
        ),
    )

    result = compute_opening_candidate_audit(
        replay=replay,
        specification=OPENING_CANDIDATE_AUDIT_V001,
        outcome_plan=plan,
        outcome_bundle=bundle,
    )

    outcomes = {item.outcome_key: item for item in result.subject_outcomes}
    assert outcomes["t_close"].maturity_status == "mature"
    assert outcomes["t1_open"].maturity_status == "mature"
    assert outcomes["t3_close"].maturity_status == "pending"
    assert outcomes["t1_open"].value_number == pytest.approx(0.06)
    assert result.summary.coverage_status == "maturing"
    assert result.replay_days[0].candidate_count == 1


def test_opening_candidate_audit_compares_production_execution_evidence() -> None:
    replay = replay_result(candidate=True)
    stage = replay.days[0].stages[0]
    production = ProductionStageEvidence(
        replay.rule_key,
        replay.rule_version,
        replay.rule_definition_hash,
        replay.days[0].trade_date,
        stage.attempt.stage_key,
        stage.attempt.attempt_key,
        stage.typed_input_fingerprint,
        stage.rule_output_fingerprint,
        "9" * 64,
    )
    as_of = AuditAsOf(date(2026, 7, 15), date(2026, 7, 14))
    plan = build_opening_candidate_outcome_plan(
        replay=replay,
        specification=OPENING_CANDIDATE_AUDIT_V001,
        as_of=as_of,
    )
    bundle = ResolvedOutcomeBundle(
        plan.identity,
        as_of,
        tuple(
            ResolvedOutcomeInput(
                item.requirement_key,
                item.query,
                pd.DataFrame(),
                (),
                content(item.requirement_key),
            )
            for item in plan.requirements
        ),
    )

    result = compute_opening_candidate_audit(
        replay=replay,
        specification=OPENING_CANDIDATE_AUDIT_V001,
        outcome_plan=plan,
        outcome_bundle=bundle,
        production_evidence=(production,),
    )

    assert result.replay_days[0].stage_parity_status == "mismatch"
    assert result.replay_stages[0].input_parity_status == "exact"
    assert result.replay_stages[0].output_parity_status == "exact"
    assert result.replay_stages[0].trace_parity_status == "mismatch"


def test_opening_candidate_audit_marks_missing_production_evidence_unavailable() -> None:
    replay = replay_result(candidate=True)
    as_of = AuditAsOf(date(2026, 7, 15), date(2026, 7, 14))
    plan = build_opening_candidate_outcome_plan(
        replay=replay,
        specification=OPENING_CANDIDATE_AUDIT_V001,
        as_of=as_of,
    )
    bundle = ResolvedOutcomeBundle(
        plan.identity,
        as_of,
        tuple(
            ResolvedOutcomeInput(
                item.requirement_key,
                item.query,
                pd.DataFrame(),
                (),
                content(item.requirement_key),
            )
            for item in plan.requirements
        ),
    )

    result = compute_opening_candidate_audit(
        replay=replay,
        specification=OPENING_CANDIDATE_AUDIT_V001,
        outcome_plan=plan,
        outcome_bundle=bundle,
    )

    assert result.replay_days[0].stage_parity_status == "unavailable"
    assert result.replay_stages[0].output_parity_status == "unavailable"


def replay_result(*, candidate: bool) -> ReplayResult:
    version = get_rule_version("opening_candidate_watch", "v001")
    trade_date = date(2026, 7, 14)
    attempt = ReplayStageAttempt(
        "generate",
        "generate.0936",
        datetime(2026, 7, 14, 9, 36, tzinfo=TZ),
    )
    output = OpeningCandidateGenerateOutput(
        status="ok",
        data_quality="normal",
        market_policy={},
        selected_industries=pd.DataFrame(),
        candidates=(
            pd.DataFrame(
                [
                    {
                        "trade_date": trade_date,
                        "symbol": "600001.SH",
                        "name": "sample",
                        "last_price": 10.0,
                        "candidate_role": "watch",
                    }
                ]
            )
            if candidate
            else pd.DataFrame()
        ),
        summary={"primary_candidate_count": int(candidate), "candidate_count": int(candidate)},
    )
    stage = ReplayStageResult(
        attempt,
        "ok",
        "normal",
        output,
        (),
        (),
        "1" * 64,
        "2" * 64,
        "3" * 64,
    )
    day = ReplayDayResult(
        "opening_candidate_watch",
        "v001",
        version.definition_hash,
        trade_date,
        (stage,),
        "ok" if candidate else "no_candidate",
        "normal",
        "4" * 64,
    )
    return ReplayResult(
        "opening_candidate_watch",
        "v001",
        version.definition_hash,
        (day,),
        {},
    )


def content(key: str) -> ContentEvidence:
    return ContentEvidence(
        1,
        1,
        1,
        (key.encode().hex() + "0" * 64)[:64],
        None,
        "normal",
        (),
    )
