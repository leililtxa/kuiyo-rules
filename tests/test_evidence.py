from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from kuiyo_rules import (
    OpeningCandidateGenerateInput,
    OpeningCandidateGenerateOutput,
    dataframe_fingerprint,
    semantic_fingerprint,
    typed_rule_contract_fingerprint,
)
from kuiyo_rules.serialization import freeze_json


TZ = ZoneInfo("Asia/Shanghai")
GENERATE_INPUT_HASH = "44dd8b4d7a9c08f71e1afae9cbc2670e685384a41816910ede3d35cb88f6315e"
GENERATE_OUTPUT_HASH = "d0ef423fd1d7779481647b1b43077f28ee8522ab3b290804c9680156bb53e3d7"


def test_dataframe_fingerprint_is_stable_across_row_and_column_order() -> None:
    first = pd.DataFrame(
        [{"symbol": "B", "value": Decimal("2.0")}, {"symbol": "A", "value": Decimal("1.0")}]
    )
    second = pd.DataFrame(
        [{"value": Decimal("1"), "symbol": "A"}, {"value": Decimal("2"), "symbol": "B"}]
    )

    assert dataframe_fingerprint(first) == dataframe_fingerprint(second)


def test_opening_candidate_typed_contract_fingerprints_are_stable() -> None:
    rule_input = OpeningCandidateGenerateInput(
        trade_date=date(2026, 7, 3),
        previous_trade_date=date(2026, 7, 2),
        cutoff_at=datetime(2026, 7, 3, 9, 36, tzinfo=TZ),
        stock_quotes=pd.DataFrame(
            [
                {"symbol": "000002.SZ", "price": Decimal("12.50")},
                {"symbol": "000001.SZ", "price": Decimal("10.00")},
            ]
        ),
        auctions=pd.DataFrame([{"symbol": "000001.SZ", "auction_price": Decimal("9.95")}]),
        daily_quotes=pd.DataFrame([{"symbol": "000001.SZ", "close": Decimal("9.80")}]),
    )
    rule_output = OpeningCandidateGenerateOutput(
        status="ok",
        data_quality="normal",
        market_policy={"signal_state": "supportive"},
        selected_industries=pd.DataFrame([{"industry_key": "801120.SI", "score": 1.25}]),
        candidates=pd.DataFrame([{"asset_key": "000001.SZ", "score": 2.5}]),
        summary={"candidate_count": 1},
    )

    assert typed_rule_contract_fingerprint(rule_input) == GENERATE_INPUT_HASH
    assert typed_rule_contract_fingerprint(rule_output) == GENERATE_OUTPUT_HASH


def test_typed_rule_contract_fingerprint_rejects_untyped_payload() -> None:
    with pytest.raises(TypeError, match="typed rule contract must be a dataclass instance"):
        typed_rule_contract_fingerprint({"status": "ok"})


def test_semantic_fingerprint_supports_time_ranges() -> None:
    assert semantic_fingerprint({"time_start": time(0, 0), "time_end": time(9, 36)})


def test_frozen_json_supports_time_ranges() -> None:
    frozen = freeze_json({"time_start": time(0, 0), "time_end": time(9, 36)})

    assert frozen["time_start"] == "00:00:00"
    assert frozen["time_end"] == "09:36:00"
