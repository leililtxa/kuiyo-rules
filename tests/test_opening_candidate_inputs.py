from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pandas as pd

from kuiyo_rules import (
    CandidateEvaluationOutput,
    OpeningCandidateGenerateOutput,
    build_generate_input,
    build_evaluation_input,
    build_tier_input,
    candidate_handoff_from_output,
    evaluation_handoff_from_output,
    typed_rule_contract_fingerprint,
)


def test_generate_input_keeps_empty_auction_schema_stable() -> None:
    value = build_generate_input(
        trade_date=date(2026, 7, 3),
        previous_trade_date=date(2026, 7, 2),
        cutoff_at=datetime(2026, 7, 3, 9, 36, tzinfo=ZoneInfo("Asia/Shanghai")),
        stock_quotes=pd.DataFrame(),
        auctions=pd.DataFrame(),
        daily_quotes=pd.DataFrame(),
    )

    assert list(value.auctions.columns) == [
        "trade_date", "symbol", "auction_price", "auction_volume_shares",
        "auction_amount_yuan", "previous_close_price", "observed_at",
    ]


def test_candidate_handoff_is_minimal_and_stable() -> None:
    output = OpeningCandidateGenerateOutput(
        status="ok",
        data_quality="normal",
        market_policy={},
        selected_industries=pd.DataFrame(),
        candidates=pd.DataFrame(
            [{
                "symbol": "000001.SZ",
                "trade_date": date(2026, 7, 3),
                "name": "Ping An",
                "candidate_rank_diversified_v0_1": 1,
                "candidate_score_live_industry_momentum_v0_1": 0.8,
                "industry_symbol": "801780.SI",
                "auction_data_quality": "normal",
            }]
        ),
        summary={},
    )

    frame = candidate_handoff_from_output(output)

    assert list(frame.columns) == [
        "candidate_key", "trade_date", "asset_type", "asset_key", "asset_name",
        "rank", "candidate_role", "score", "metrics", "data_quality",
    ]
    assert frame.iloc[0]["metrics"] == {"auction_data_quality": "normal"}


def test_candidate_handoff_uses_stable_score_precision() -> None:
    output = OpeningCandidateGenerateOutput(
        status="ok",
        data_quality="normal",
        market_policy={},
        selected_industries=pd.DataFrame(),
        candidates=pd.DataFrame(
            [{
                "symbol": "000001.SZ",
                "trade_date": date(2026, 7, 3),
                "candidate_score_live_industry_momentum_v0_1": 0.9047058823529412,
            }]
        ),
        summary={},
    )

    assert candidate_handoff_from_output(output).iloc[0]["score"] == 0.904705882352941


def test_evaluation_handoff_only_keeps_tier_contract_metrics() -> None:
    output = CandidateEvaluationOutput(
        status="ok",
        data_quality="normal",
        evaluations=pd.DataFrame(
            [{
                "candidate_key": "000001.SZ",
                "decision": "confirmed",
                "score": 0.7,
                "tags": {},
                "metrics": {
                    "candidate_price": 10.0,
                    "candidate_time_label": "09:36",
                    "unused_diagnostic": 1,
                },
                "data_quality": "normal",
                "asset_key": "000001.SZ",
            }]
        ),
        summary={},
    )

    frame = evaluation_handoff_from_output(output)

    assert list(frame.columns) == [
        "candidate_key", "decision", "score", "tags", "metrics", "data_quality",
    ]
    assert frame.iloc[0]["metrics"] == {"candidate_price": 10.0}


def test_evaluation_input_normalizes_loader_numeric_types_and_display_columns() -> None:
    common = {
        "trade_date": date(2026, 7, 3),
        "candidate_cutoff_at": datetime(2026, 7, 3, 9, 36, tzinfo=ZoneInfo("Asia/Shanghai")),
        "evaluation_cutoff_at": datetime(2026, 7, 3, 9, 46, tzinfo=ZoneInfo("Asia/Shanghai")),
        "candidates": pd.DataFrame([candidate_row()]),
        "candidate_industries": pd.DataFrame(
            [{"symbol": "000001.SZ", "industry_symbol": "801780.SI", "industry_name": "Bank"}]
        ),
        "industry_members": pd.DataFrame(
            [{"symbol": "000001.SZ", "industry_symbol": "801780.SI"}]
        ),
    }
    production = build_evaluation_input(
        **common,
        stock_quotes=quote_frame(10.0),
        industry_quotes=industry_quote_frame(10.0, include_name=True),
        index_quotes=index_quote_frame(10.0, include_name=True),
    )
    replay = build_evaluation_input(
        **common,
        stock_quotes=quote_frame(Decimal("10.0")),
        industry_quotes=industry_quote_frame(Decimal("10.0")),
        index_quotes=index_quote_frame(Decimal("10.0")),
    )

    assert typed_rule_contract_fingerprint(production) == typed_rule_contract_fingerprint(replay)


def test_tier_input_normalizes_full_and_persisted_evaluation_handoffs() -> None:
    common = {
        "trade_date": date(2026, 7, 3),
        "cutoff_at": datetime(2026, 7, 3, 9, 46, tzinfo=ZoneInfo("Asia/Shanghai")),
        "candidates": pd.DataFrame([candidate_row()]),
    }
    full = build_tier_input(
        **common,
        evaluations=pd.DataFrame(
            [{
                "candidate_key": "000001.SZ", "decision": "confirmed", "score": 0.7,
                "tags": {}, "metrics": {"candidate_price": 10.0, "unused": 1},
                "data_quality": "normal", "diagnostic": "full",
            }]
        ),
    )
    persisted = build_tier_input(
        **common,
        evaluations=pd.DataFrame(
            [{
                "candidate_key": "000001.SZ", "decision": "confirmed", "score": 0.7,
                "tags": {},
                "metrics": {"candidate_price": 10.0, "candidate_time_label": "09:36"},
                "data_quality": "normal",
            }]
        ),
    )

    assert typed_rule_contract_fingerprint(full) == typed_rule_contract_fingerprint(persisted)


def candidate_row() -> dict[str, object]:
    return {
        "candidate_key": "000001.SZ", "trade_date": date(2026, 7, 3),
        "asset_type": "stock", "asset_key": "000001.SZ", "asset_name": "Ping An",
        "rank": 1, "candidate_role": "watch", "score": 0.8, "metrics": {},
        "data_quality": "normal",
    }


def quote_frame(value: object) -> pd.DataFrame:
    return pd.DataFrame(
        [{
            "trade_date": date(2026, 7, 3), "snapshot_at": "2026-07-03 09:35:00+08:00",
            "quote_time": "2026-07-03 09:35:00+08:00", "symbol": "000001.SZ",
            "previous_close_price": value, "open_price": value, "last_price": value,
            "volume_shares": value, "turnover_amount_yuan": value,
        }]
    )


def industry_quote_frame(value: object, *, include_name: bool = False) -> pd.DataFrame:
    frame = quote_frame(value).assign(classification_system="sw2021", pct_change=value)
    if include_name:
        frame["name"] = "Bank"
    return frame


def index_quote_frame(value: object, *, include_name: bool = False) -> pd.DataFrame:
    frame = quote_frame(value).rename(columns={"volume_shares": "volume"})
    if include_name:
        frame["name"] = "Index"
    return frame
