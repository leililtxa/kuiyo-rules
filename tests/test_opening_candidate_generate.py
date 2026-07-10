from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pandas as pd
from pandas.testing import assert_frame_equal

from kuiyo_rules import (
    OpeningCandidateGenerateInput,
    generate_opening_candidates,
)
from kuiyo_rules.clauses import RuleClauseReference
from kuiyo_rules.definitions import OPENING_CANDIDATE_BASELINE_V001, ResearchRuleVersion


TRADE_DATE = date(2026, 6, 22)
PREVIOUS_TRADE_DATE = date(2026, 6, 19)
CUTOFF_AT = datetime(2026, 6, 22, 9, 36, tzinfo=ZoneInfo("Asia/Shanghai"))


def test_generate_opening_candidates_matches_baseline_characterization() -> None:
    output = generate_opening_candidates(
        rule_version=build_test_rule_version(),
        rule_input=rule_input(),
    )

    assert output.status == "ok"
    assert output.data_quality == "normal"
    assert list(output.candidates["symbol"]) == ["600001.SH", "600002.SH"]
    assert list(output.candidates["candidate_key"]) == ["600001.SH", "600002.SH"]
    assert list(output.candidates["candidate_rank_diversified_v0_1"]) == [1, 2]
    assert output.summary["primary_candidate_count"] == 2
    assert output.summary["shadow_candidate_count"] == 0
    assert output.summary["rule"]["rule_version"] == "v001"


def test_generate_opening_candidates_is_deterministic() -> None:
    version = build_test_rule_version()
    inputs = rule_input()

    first = generate_opening_candidates(rule_version=version, rule_input=inputs)
    second = generate_opening_candidates(rule_version=version, rule_input=inputs)

    assert first.status == second.status
    assert first.data_quality == second.data_quality
    assert first.market_policy == second.market_policy
    assert first.summary == second.summary
    assert_frame_equal(first.selected_industries, second.selected_industries)
    assert_frame_equal(first.candidates, second.candidates)
    assert_frame_equal(first.ranked_pool, second.ranked_pool)


def test_generate_opening_candidates_reports_missing_stock_window() -> None:
    output = generate_opening_candidates(
        rule_version=build_test_rule_version(),
        rule_input=replace(rule_input(), stock_quotes=pd.DataFrame()),
    )

    assert output.status == "missing_data"
    assert output.data_quality == "missing"
    assert output.market_policy["reason"] == "no_realtime_before_cutoff"
    assert output.candidates.empty


def test_generate_opening_candidates_rejects_missing_previous_daily() -> None:
    inputs = rule_input()
    daily_quotes = inputs.daily_quotes[
        inputs.daily_quotes["trade_date"] != PREVIOUS_TRADE_DATE
    ].copy()

    output = generate_opening_candidates(
        rule_version=build_test_rule_version(),
        rule_input=replace(inputs, daily_quotes=daily_quotes),
    )

    assert output.status == "missing_data"
    assert output.data_quality == "missing"
    assert output.market_policy["policy_suggestion"] == "data_gap_observe_only"
    assert output.candidates.empty


def test_generate_opening_candidates_keeps_shadow_pool_separate() -> None:
    output = generate_opening_candidates(
        rule_version=build_test_rule_version(),
        rule_input=rule_input(
            stock_quotes=moderate_stock_quotes(),
            auctions=moderate_auctions(),
            daily_quotes=weak_market_daily_quotes(),
        ),
    )

    assert output.status == "ok"
    assert output.data_quality == "normal"
    assert list(output.candidates["symbol"]) == ["600001.SH"]
    assert list(output.candidates["candidate_role"]) == ["shadow"]
    assert output.summary["primary_candidate_count"] == 0
    assert output.summary["shadow_candidate_count"] == 1
    assert output.market_policy["policy_suggestion"] == "no_trade"


def test_generate_opening_candidates_preserves_auction_proxy_quality_baseline() -> None:
    inputs = rule_input()
    output = generate_opening_candidates(
        rule_version=build_test_rule_version(),
        rule_input=replace(inputs, auctions=pd.DataFrame()),
    )

    assert output.status == "ok"
    assert output.data_quality == "partial"
    assert set(output.candidates["auction_data_quality"]) == {"missing"}


def test_generate_opening_candidates_marks_stale_snapshot_without_candidates() -> None:
    inputs = rule_input()
    stock_quotes = inputs.stock_quotes.copy()
    stale_at = datetime(2026, 6, 22, 9, 30, tzinfo=ZoneInfo("Asia/Shanghai"))
    stock_quotes["snapshot_at"] = stale_at
    stock_quotes["quote_time"] = stale_at

    output = generate_opening_candidates(
        rule_version=build_test_rule_version(),
        rule_input=replace(inputs, stock_quotes=stock_quotes),
    )

    assert output.status == "no_candidate"
    assert output.data_quality == "degraded"
    assert output.market_policy["snapshot_quality"] == "stale"
    assert output.candidates.empty


def test_generate_parameters_are_read_from_rule_artifact() -> None:
    version = build_test_rule_version(minimum_return_previous_close=0.10)

    output = generate_opening_candidates(rule_version=version, rule_input=rule_input())

    assert output.status == "no_candidate"
    assert output.candidates.empty
    assert not output.ranked_pool.empty
    assert not output.ranked_pool["stock_rule_pass_ret_prev_close_0935_gt_0"].any()


def test_rule_input_frames_are_not_mutated() -> None:
    inputs = rule_input()
    stock_quotes = inputs.stock_quotes.copy(deep=True)
    auctions = inputs.auctions.copy(deep=True)
    daily_quotes = inputs.daily_quotes.copy(deep=True)

    generate_opening_candidates(rule_version=build_test_rule_version(), rule_input=inputs)

    assert_frame_equal(inputs.stock_quotes, stock_quotes)
    assert_frame_equal(inputs.auctions, auctions)
    assert_frame_equal(inputs.daily_quotes, daily_quotes)


def test_rule_evaluator_does_not_add_database_identity() -> None:
    output = generate_opening_candidates(
        rule_version=build_test_rule_version(),
        rule_input=rule_input(),
    )

    forbidden = {
        "id",
        "job_run_id",
        "research_candidate_set_id",
        "research_candidate_id",
    }
    assert forbidden.isdisjoint(output.candidates.columns)


def build_test_rule_version(
    *,
    minimum_return_previous_close: float = 0.0,
) -> ResearchRuleVersion:
    replacements = {
        "opening.industry-strength": {
            "minimum_members": 1,
            "normal_limit": 2,
        },
        "opening.candidate-scoring": {"max_stocks_per_industry": 1},
        "opening.stock-eligibility": {
            "minimum_return_previous_close": minimum_return_previous_close,
        },
    }
    clauses: list[RuleClauseReference] = []
    for clause in OPENING_CANDIDATE_BASELINE_V001.clause_composition:
        parameters = dict(clause.parameters)
        parameters.update(replacements.get(clause.clause_key, {}))
        clauses.append(replace(clause, parameters=parameters))
    return replace(OPENING_CANDIDATE_BASELINE_V001, clause_composition=tuple(clauses))


def rule_input(
    *,
    stock_quotes: pd.DataFrame | None = None,
    auctions: pd.DataFrame | None = None,
    daily_quotes: pd.DataFrame | None = None,
) -> OpeningCandidateGenerateInput:
    return OpeningCandidateGenerateInput(
        trade_date=TRADE_DATE,
        previous_trade_date=PREVIOUS_TRADE_DATE,
        cutoff_at=CUTOFF_AT,
        stock_quotes=stock_quotes if stock_quotes is not None else frame(stock_quote_rows()),
        auctions=auctions if auctions is not None else frame(auction_rows()),
        daily_quotes=daily_quotes if daily_quotes is not None else frame(daily_quote_rows()),
    )


def stock_quote_rows() -> list[dict[str, object]]:
    snapshot_at = datetime(2026, 6, 22, 9, 35, 30, tzinfo=ZoneInfo("Asia/Shanghai"))
    return [
        stock_quote(
            snapshot_at=snapshot_at,
            symbol="600001.SH",
            name="Huiquan",
            previous_close=11.0,
            open_price=11.2,
            last_price=11.6,
            amount=1_160_000,
            industry_symbol="801120.SI",
            industry_name="Food",
        ),
        stock_quote(
            snapshot_at=snapshot_at,
            symbol="600002.SH",
            name="Chemical",
            previous_close=22.0,
            open_price=22.1,
            last_price=22.5,
            amount=2_025_000,
            industry_symbol="801030.SI",
            industry_name="Chemical",
        ),
        stock_quote(
            snapshot_at=snapshot_at,
            symbol="600003.SH",
            name="ST Risk",
            previous_close=8.0,
            open_price=8.05,
            last_price=8.1,
            amount=648_000,
            industry_symbol="801120.SI",
            industry_name="Food",
        ),
    ]


def stock_quote(
    *,
    snapshot_at: datetime,
    symbol: str,
    name: str,
    previous_close: float,
    open_price: float,
    last_price: float,
    amount: float,
    industry_symbol: str,
    industry_name: str,
) -> dict[str, object]:
    return {
        "trade_date": TRADE_DATE,
        "snapshot_at": snapshot_at,
        "quote_time": snapshot_at,
        "symbol": symbol,
        "name": name,
        "exchange": "SH",
        "market": "Main",
        "listing_status": "listed",
        "previous_close_price": previous_close,
        "open_price": open_price,
        "last_price": last_price,
        "volume_shares": 100_000,
        "turnover_amount_yuan": amount,
        "industry_symbol": industry_symbol,
        "industry_name": industry_name,
    }


def auction_rows() -> list[dict[str, object]]:
    observed_at = datetime(2026, 6, 22, 9, 29, tzinfo=ZoneInfo("Asia/Shanghai"))
    values = {
        "600001.SH": (11.15, 11.0),
        "600002.SH": (22.05, 22.0),
        "600003.SH": (8.02, 8.0),
    }
    return [
        {
            "trade_date": TRADE_DATE,
            "symbol": symbol,
            "auction_price": auction_price,
            "auction_volume_shares": 10_000,
            "auction_amount_yuan": auction_price * 10_000,
            "previous_close_price": previous_close,
            "observed_at": observed_at,
        }
        for symbol, (auction_price, previous_close) in values.items()
    ]


def daily_quote_rows() -> list[dict[str, object]]:
    closes_by_symbol = {
        "600001.SH": [10.0, 10.2, 10.4, 10.6, 10.8, 11.0],
        "600002.SH": [20.0, 20.4, 20.8, 21.2, 21.6, 22.0],
        "600003.SH": [7.5, 7.6, 7.7, 7.8, 7.9, 8.0],
    }
    return build_daily_rows(closes_by_symbol)


def moderate_stock_quotes() -> pd.DataFrame:
    snapshot_at = datetime(2026, 6, 22, 9, 35, 30, tzinfo=ZoneInfo("Asia/Shanghai"))
    return frame(
        [
            stock_quote(
                snapshot_at=snapshot_at,
                symbol="600001.SH",
                name="Moderate One",
                previous_close=10.0,
                open_price=10.05,
                last_price=10.10,
                amount=1_010_000,
                industry_symbol="801120.SI",
                industry_name="Food",
            ),
            stock_quote(
                snapshot_at=snapshot_at,
                symbol="600002.SH",
                name="Moderate Two",
                previous_close=10.0,
                open_price=10.0,
                last_price=9.96,
                amount=896_400,
                industry_symbol="801120.SI",
                industry_name="Food",
            ),
        ]
    )


def moderate_auctions() -> pd.DataFrame:
    observed_at = datetime(2026, 6, 22, 9, 29, tzinfo=ZoneInfo("Asia/Shanghai"))
    return frame(
        [
            {
                "trade_date": TRADE_DATE,
                "symbol": "600001.SH",
                "auction_price": 10.02,
                "auction_volume_shares": 10_000,
                "auction_amount_yuan": 100_200,
                "previous_close_price": 10.0,
                "observed_at": observed_at,
            },
            {
                "trade_date": TRADE_DATE,
                "symbol": "600002.SH",
                "auction_price": 9.99,
                "auction_volume_shares": 9_000,
                "auction_amount_yuan": 89_910,
                "previous_close_price": 10.0,
                "observed_at": observed_at,
            },
        ]
    )


def weak_market_daily_quotes() -> pd.DataFrame:
    closes_by_symbol = {
        "600001.SH": [9.7, 9.8, 9.9, 9.95, 10.0, 10.02],
        "600002.SH": [10.2, 10.15, 10.1, 10.08, 10.05, 9.98],
        "600004.SH": [8.2, 8.18, 8.15, 8.12, 8.1, 8.0],
    }
    return frame(build_daily_rows(closes_by_symbol))


def build_daily_rows(closes_by_symbol: dict[str, list[float]]) -> list[dict[str, object]]:
    trading_days = [
        date(2026, 6, 12),
        date(2026, 6, 15),
        date(2026, 6, 16),
        date(2026, 6, 17),
        date(2026, 6, 18),
        PREVIOUS_TRADE_DATE,
    ]
    rows: list[dict[str, object]] = []
    for symbol, closes in closes_by_symbol.items():
        previous_close = closes[0] - 0.1
        for trading_date, close_price in zip(trading_days, closes, strict=True):
            rows.append(
                {
                    "trade_date": trading_date,
                    "symbol": symbol,
                    "close_price": close_price,
                    "previous_close_price": previous_close,
                }
            )
            previous_close = close_price
    return rows


def frame(rows: list[dict[str, object]]) -> pd.DataFrame:
    output = pd.DataFrame(rows)
    if "trade_date" in output:
        output["trade_date"] = pd.to_datetime(output["trade_date"]).dt.date
    for column in ("snapshot_at", "quote_time", "observed_at"):
        if column in output:
            output[column] = pd.to_datetime(output[column])
    if {"close_price", "previous_close_price"}.issubset(output.columns):
        output["day_ret"] = output["close_price"] / output["previous_close_price"] - 1.0
    return output
