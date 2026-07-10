from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pandas as pd
from pandas.testing import assert_frame_equal

from kuiyo_rules import (
    CandidateEvaluationInput,
    CandidateTierInput,
    evaluate_opening_candidates,
    tier_opening_candidates,
)
from kuiyo_rules.definitions import OPENING_CANDIDATE_BASELINE_V001
from kuiyo_rules.evaluation.opening_candidate.evaluation_rules import (
    apply_execution_confirmation,
)
from kuiyo_rules.evaluation.opening_candidate.parameters import (
    evaluation_parameters,
    tier_parameters,
)
from kuiyo_rules.evaluation.opening_candidate.tier_features import live_timing_state


TRADE_DATE = date(2026, 6, 22)
CANDIDATE_CUTOFF_AT = datetime(
    2026,
    6,
    22,
    9,
    36,
    tzinfo=ZoneInfo("Asia/Shanghai"),
)
EVALUATION_CUTOFF_AT = datetime(
    2026,
    6,
    22,
    9,
    41,
    tzinfo=ZoneInfo("Asia/Shanghai"),
)


def test_evaluate_opening_candidates_matches_baseline_characterization() -> None:
    output = evaluate_opening_candidates(
        rule_version=OPENING_CANDIDATE_BASELINE_V001,
        rule_input=evaluation_input(),
    )

    assert output.status == "ok"
    assert output.data_quality == "normal"
    assert list(output.evaluations["candidate_key"]) == ["600001.SH", "600002.SH"]
    assert list(output.evaluations["decision"]) == ["strong_confirm", "reject"]
    assert list(output.evaluations["score"]) == [5, -8]
    assert output.evaluations.iloc[0]["execution_reference_price"] == 10.65
    assert output.evaluations.iloc[0]["max_execution_premium"] == 0.01
    assert output.evaluations.iloc[0]["chase_risk_level"] == "elevated"
    assert output.summary["decision_counts"] == {"strong_confirm": 1, "reject": 1}


def test_evaluate_opening_candidates_is_deterministic_and_does_not_mutate_inputs() -> None:
    inputs = evaluation_input()
    candidates = inputs.candidates.copy(deep=True)
    stock_quotes = inputs.stock_quotes.copy(deep=True)

    first = evaluate_opening_candidates(
        rule_version=OPENING_CANDIDATE_BASELINE_V001,
        rule_input=inputs,
    )
    second = evaluate_opening_candidates(
        rule_version=OPENING_CANDIDATE_BASELINE_V001,
        rule_input=inputs,
    )

    assert first.summary == second.summary
    assert_frame_equal(first.evaluations, second.evaluations)
    assert_frame_equal(inputs.candidates, candidates)
    assert_frame_equal(inputs.stock_quotes, stock_quotes)


def test_evaluate_opening_candidates_marks_missing_checkpoint_invalid() -> None:
    inputs = evaluation_input()
    stock_quotes = inputs.stock_quotes[
        ~inputs.stock_quotes["symbol"].eq("600001.SH")
    ].copy()
    output = evaluate_opening_candidates(
        rule_version=OPENING_CANDIDATE_BASELINE_V001,
        rule_input=replace(inputs, stock_quotes=stock_quotes),
    )

    first = output.evaluations.iloc[0]
    assert first["decision"] == "invalid"
    assert first["hard_tags"] == ["missing_stock_checkpoint"]
    assert first["data_quality"] == "missing"


def test_execution_confirmation_keeps_shadow_candidate_as_observe() -> None:
    parameters = evaluation_parameters(OPENING_CANDIDATE_BASELINE_V001)
    evaluated = apply_execution_confirmation(
        pd.DataFrame(
            [
                {
                    "candidate_role": "shadow",
                    "candidate_price": 10.0,
                    "execution_price": 10.2,
                    "stock_candidate_execution_ret": 0.02,
                    "execution_ret_prev_close": 0.02,
                    "execution_ret_open": 0.01,
                    "industry_execution_up_ratio": 0.7,
                    "industry_execution_up_ratio_delta": 0.1,
                    "industry_execution_avg_ret_delta": 0.01,
                    "industry_execution_strong_3pct_delta": 1,
                }
            ]
        ),
        parameters=parameters,
    )

    assert evaluated.iloc[0]["decision"] == "observe"
    assert "shadow_diagnostic_only" in evaluated.iloc[0]["soft_tags"]


def test_chase_risk_boundaries_are_preserved() -> None:
    parameters = evaluation_parameters(OPENING_CANDIDATE_BASELINE_V001)
    features = pd.DataFrame(
        [
            execution_feature(0.0499),
            execution_feature(0.05),
            execution_feature(0.08),
        ]
    )

    evaluated = apply_execution_confirmation(features, parameters=parameters)

    assert list(evaluated["chase_risk_level"]) == ["normal", "elevated", "high"]


def test_tier_opening_candidates_matches_baseline_characterization() -> None:
    evaluated = evaluate_opening_candidates(
        rule_version=OPENING_CANDIDATE_BASELINE_V001,
        rule_input=evaluation_input(),
    )
    output = tier_opening_candidates(
        rule_version=OPENING_CANDIDATE_BASELINE_V001,
        rule_input=CandidateTierInput(
            trade_date=TRADE_DATE,
            cutoff_at=EVALUATION_CUTOFF_AT,
            candidates=candidate_frame(),
            evaluations=evaluated.evaluations,
        ),
    )

    assert output.status == "ok"
    assert output.data_quality == "normal"
    assert list(output.tiers["candidate_key"]) == ["600001.SH", "600002.SH"]
    assert list(output.tiers["watch_level"]) == ["secondary_watch", "reject"]
    assert list(output.tiers["priority"]) == [1, 2]
    assert output.tiers.iloc[0]["reasons"] == ("has_soft_confirm_but_not_focus",)


def test_tier_opening_candidates_reports_missing_upstream_evaluation() -> None:
    output = tier_opening_candidates(
        rule_version=OPENING_CANDIDATE_BASELINE_V001,
        rule_input=CandidateTierInput(
            trade_date=TRADE_DATE,
            cutoff_at=EVALUATION_CUTOFF_AT,
            candidates=candidate_frame(),
            evaluations=pd.DataFrame(),
        ),
    )

    assert output.status == "upstream_no_evaluation"
    assert output.data_quality == "missing"
    assert output.tiers.empty


def test_tier_forces_shadow_candidate_to_observe_only() -> None:
    candidates = candidate_frame().iloc[[0]].copy()
    candidates["candidate_role"] = "shadow"
    evaluations = pd.DataFrame(
        [
            {
                "candidate_key": "600001.SH",
                "decision": "strong_confirm",
                "score": 5,
                "tags": {"hard": [], "soft": ["confirm_stock_continuation_execution"]},
                "metrics": {
                    "candidate_price": 10.5,
                    "candidate_ret_prev_close": 0.05,
                    "execution_reference_price": 10.65,
                    "stock_candidate_execution_ret": 0.014,
                    "chase_risk_level": "normal",
                },
                "data_quality": "normal",
            }
        ]
    )

    output = tier_opening_candidates(
        rule_version=OPENING_CANDIDATE_BASELINE_V001,
        rule_input=CandidateTierInput(
            trade_date=TRADE_DATE,
            cutoff_at=EVALUATION_CUTOFF_AT,
            candidates=candidates,
            evaluations=evaluations,
        ),
    )

    assert output.tiers.iloc[0]["watch_level"] == "observe_only"
    assert output.tiers.iloc[0]["reasons"] == ("shadow_diagnostic_only",)


def test_live_timing_boundaries_are_preserved() -> None:
    parameters = tier_parameters(OPENING_CANDIDATE_BASELINE_V001)
    base = {
        "evaluation_decision": "confirm",
        "candidate_price": 10.0,
        "execution_reference_price": 10.0,
        "candidate_ret_prev_close": 0.0,
    }

    assert live_timing_state(
        {**base, "stock_candidate_execution_ret": -0.0101},
        parameters=parameters,
    ) == "faded_before_execution"
    assert live_timing_state(
        {**base, "stock_candidate_execution_ret": -0.005},
        parameters=parameters,
    ) == "stable_after_candidate_cutoff"
    assert live_timing_state(
        {**base, "stock_candidate_execution_ret": 0.005},
        parameters=parameters,
    ) == "continued_after_candidate_cutoff"
    assert live_timing_state(
        {**base, "candidate_ret_prev_close": 0.07, "stock_candidate_execution_ret": 0.01},
        parameters=parameters,
    ) == "already_hot_by_candidate_cutoff"


def test_evaluation_and_tier_outputs_do_not_contain_database_identity() -> None:
    evaluated = evaluate_opening_candidates(
        rule_version=OPENING_CANDIDATE_BASELINE_V001,
        rule_input=evaluation_input(),
    )
    tiered = tier_opening_candidates(
        rule_version=OPENING_CANDIDATE_BASELINE_V001,
        rule_input=CandidateTierInput(
            trade_date=TRADE_DATE,
            cutoff_at=EVALUATION_CUTOFF_AT,
            candidates=candidate_frame(),
            evaluations=evaluated.evaluations,
        ),
    )
    forbidden = {
        "id",
        "job_run_id",
        "research_candidate_id",
        "research_candidate_set_id",
        "research_candidate_evaluation_id",
    }

    assert forbidden.isdisjoint(evaluated.evaluations.columns)
    assert forbidden.isdisjoint(tiered.tiers.columns)


def evaluation_input() -> CandidateEvaluationInput:
    return CandidateEvaluationInput(
        trade_date=TRADE_DATE,
        candidate_cutoff_at=CANDIDATE_CUTOFF_AT,
        evaluation_cutoff_at=EVALUATION_CUTOFF_AT,
        candidates=candidate_frame(),
        stock_quotes=stock_quote_frame(),
        candidate_industries=pd.DataFrame(
            [
                {"symbol": "600001.SH", "industry_symbol": "801120.SI", "industry_name": "Food"},
                {"symbol": "600002.SH", "industry_symbol": "801030.SI", "industry_name": "Chemical"},
            ]
        ),
        industry_members=pd.DataFrame(
            [
                {"symbol": "600001.SH", "industry_symbol": "801120.SI"},
                {"symbol": "600003.SH", "industry_symbol": "801120.SI"},
                {"symbol": "600002.SH", "industry_symbol": "801030.SI"},
                {"symbol": "600004.SH", "industry_symbol": "801030.SI"},
            ]
        ),
        industry_quotes=industry_quote_frame(),
        index_quotes=index_quote_frame(),
    )


def candidate_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            candidate("600001.SH", "Huiquan", 1, 0.9),
            candidate("600002.SH", "Chemical", 2, 0.8),
        ]
    )


def candidate(asset_key: str, asset_name: str, rank: int, score: float) -> dict[str, object]:
    return {
        "candidate_key": asset_key,
        "trade_date": TRADE_DATE,
        "asset_type": "stock",
        "asset_key": asset_key,
        "asset_name": asset_name,
        "rank": rank,
        "candidate_role": "watch",
        "score": score,
        "metrics": {"candidate_score": score},
        "data_quality": "normal",
    }


def stock_quote_frame() -> pd.DataFrame:
    rows = [
        stock_quote("600001.SH", "09:35:30", 10.0, 10.1, 10.5),
        stock_quote("600001.SH", "09:40:30", 10.0, 10.1, 10.65),
        stock_quote("600003.SH", "09:35:30", 5.0, 5.0, 5.1),
        stock_quote("600003.SH", "09:40:30", 5.0, 5.0, 5.15),
        stock_quote("600002.SH", "09:35:30", 20.0, 20.4, 20.5),
        stock_quote("600002.SH", "09:40:30", 20.0, 20.4, 20.3),
        stock_quote("600004.SH", "09:35:30", 8.0, 8.0, 8.1),
        stock_quote("600004.SH", "09:40:30", 8.0, 8.0, 8.0),
    ]
    return pd.DataFrame(rows)


def stock_quote(
    symbol: str,
    clock: str,
    previous_close: float,
    open_price: float,
    last_price: float,
) -> dict[str, object]:
    snapshot_at = aware(f"2026-06-22T{clock}")
    return {
        "trade_date": TRADE_DATE,
        "snapshot_at": snapshot_at,
        "quote_time": snapshot_at,
        "symbol": symbol,
        "previous_close_price": previous_close,
        "open_price": open_price,
        "last_price": last_price,
        "volume_shares": 10_000,
        "turnover_amount_yuan": last_price * 10_000,
    }


def industry_quote_frame() -> pd.DataFrame:
    rows = [
        quote("801120.SI", "09:35:30", 1000, 1005, 1020),
        quote("801120.SI", "09:40:30", 1000, 1005, 1030),
        quote("801030.SI", "09:35:30", 2000, 2010, 2030),
        quote("801030.SI", "09:40:30", 2000, 2010, 2020),
    ]
    return pd.DataFrame(rows)


def index_quote_frame() -> pd.DataFrame:
    rows = [
        quote("000001.SH", "09:35:30", 3000, 3001, 3005),
        quote("000001.SH", "09:40:30", 3000, 3001, 3010),
        quote("000852.SH", "09:35:30", 6000, 6010, 6020),
        quote("000852.SH", "09:40:30", 6000, 6010, 6015),
    ]
    return pd.DataFrame(rows)


def quote(
    symbol: str,
    clock: str,
    previous_close: float,
    open_price: float,
    last_price: float,
) -> dict[str, object]:
    snapshot_at = aware(f"2026-06-22T{clock}")
    return {
        "trade_date": TRADE_DATE,
        "snapshot_at": snapshot_at,
        "quote_time": snapshot_at,
        "symbol": symbol,
        "previous_close_price": previous_close,
        "open_price": open_price,
        "last_price": last_price,
    }


def execution_feature(execution_return: float) -> dict[str, object]:
    return {
        "candidate_role": "watch",
        "candidate_price": 10.0,
        "execution_price": 10.1,
        "stock_candidate_execution_ret": 0.01,
        "execution_ret_prev_close": execution_return,
        "execution_ret_open": 0.01,
        "industry_execution_up_ratio": 0.7,
        "industry_execution_up_ratio_delta": 0.1,
        "industry_execution_avg_ret_delta": 0.01,
        "industry_execution_strong_3pct_delta": 1,
    }


def aware(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=ZoneInfo("Asia/Shanghai"))
