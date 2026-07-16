from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pandas as pd

from kuiyo_rules import (
    ContentEvidence,
    OpeningCandidateGenerateInput,
    QueryIntent,
    ResolutionEvidence,
    dataframe_fingerprint,
    get_rule_version,
)
from kuiyo_rules.replay.opening_candidate import generate_execution_evidence


TZ = ZoneInfo("Asia/Shanghai")
DAY = date(2026, 7, 3)
CUTOFF = datetime(2026, 7, 3, 9, 36, tzinfo=TZ)


def test_generate_evidence_uses_consumed_input_not_raw_resolution() -> None:
    stock_quotes = pd.DataFrame(
        [
            {
                "trade_date": DAY,
                "snapshot_at": datetime(2026, 7, 3, 9, 35, tzinfo=TZ),
                "quote_time": datetime(2026, 7, 3, 9, 35, tzinfo=TZ),
                "symbol": "600573.SH",
            }
        ]
    )
    rule_input = OpeningCandidateGenerateInput(
        trade_date=DAY,
        previous_trade_date=date(2026, 7, 2),
        cutoff_at=CUTOFF,
        stock_quotes=stock_quotes,
        auctions=pd.DataFrame(),
        daily_quotes=pd.DataFrame(
            [
                {
                    "trade_date": date(2026, 7, 2),
                    "symbol": "600573.SH",
                    "close_price": 10.0,
                }
            ]
        ),
    )
    resolutions = {
        key: resolution(key)
        for key in (
            "generate.trading_calendar",
            "generate.universe",
            "generate.stock_reference",
            "generate.classification",
            "generate.industry_reference",
            "generate.stock_window",
            "generate.stock_auction",
            "generate.stock_daily",
        )
    }

    evidence = generate_execution_evidence(
        rule_input,
        rule_version=get_rule_version("opening_candidate_watch", "v001"),
        resolutions=resolutions,
    )
    by_key = {item.query.input_key: item for item in evidence}

    assert set(by_key) == {
        "generate.previous_trade_date",
        "generate.stock_quotes",
        "generate.auctions",
        "generate.daily_quotes",
    }
    assert (
        by_key["generate.stock_quotes"].content.content_fingerprint
        == dataframe_fingerprint(stock_quotes)
    )
    assert (
        by_key["generate.stock_quotes"].content.content_fingerprint
        != resolutions["generate.stock_reference"].content.content_fingerprint
    )
    assert by_key["generate.stock_quotes"].conformance.status == "valid"
    assert by_key["generate.auctions"].conformance.status == "degraded"
    assert by_key["generate.auctions"].conformance.reasons == (
        "auction_input_empty_proxy_possible",
    )


def resolution(input_key: str) -> ResolutionEvidence:
    return ResolutionEvidence(
        query=QueryIntent(
            input_key=input_key,
            input_type="dataset",
            requested_range={"date_start": DAY, "date_end": DAY},
            dataset_key="market.test.dataset.daily",
        ),
        resolved_sources=(),
        content=ContentEvidence(
            row_count=10,
            entity_count=10,
            observation_count=10,
            content_fingerprint="f" * 64,
            min_known_at="2010-01-01T00:00:00+08:00",
            max_known_at="2099-01-01T00:00:00+08:00",
            quality="normal",
            quality_reasons=(),
        ),
        captured_at=datetime(2026, 7, 15, 19, 0, tzinfo=TZ),
    )
