from __future__ import annotations

from datetime import date, datetime
from typing import Any

import pandas as pd

from kuiyo_rules.contracts.opening_candidate import (
    CandidateEvaluationInput,
    CandidateEvaluationOutput,
    CandidateTierInput,
    OpeningCandidateGenerateInput,
    OpeningCandidateGenerateOutput,
)
from kuiyo_rules.numeric import none_float
from kuiyo_rules.quality import materialized_data_quality


GENERATE_STOCK_QUOTE_COLUMNS = (
    "trade_date", "snapshot_at", "quote_time", "symbol", "previous_close_price",
    "open_price", "last_price", "volume_shares", "turnover_amount_yuan", "name",
    "exchange", "market", "listing_status", "industry_symbol", "industry_name",
)
GENERATE_AUCTION_COLUMNS = (
    "trade_date", "symbol", "auction_price", "auction_volume_shares",
    "auction_amount_yuan", "previous_close_price", "observed_at",
)
GENERATE_DAILY_COLUMNS = (
    "trade_date", "symbol", "close_price", "previous_close_price", "day_ret",
)
CANDIDATE_HANDOFF_COLUMNS = (
    "candidate_key", "trade_date", "asset_type", "asset_key", "asset_name", "rank",
    "candidate_role", "score", "metrics", "data_quality",
)
EVALUATION_STOCK_QUOTE_COLUMNS = (
    "trade_date", "snapshot_at", "quote_time", "symbol", "previous_close_price",
    "open_price", "last_price", "volume_shares", "turnover_amount_yuan",
)
EVALUATION_INDUSTRY_QUOTE_COLUMNS = (
    "trade_date", "snapshot_at", "quote_time", "classification_system", "symbol",
    "previous_close_price", "open_price", "last_price", "pct_change", "volume_shares",
    "turnover_amount_yuan",
)
EVALUATION_INDEX_QUOTE_COLUMNS = (
    "trade_date", "snapshot_at", "quote_time", "symbol", "previous_close_price",
    "open_price", "last_price", "volume", "turnover_amount_yuan",
)
EVALUATION_HANDOFF_COLUMNS = (
    "candidate_key", "decision", "score", "tags", "metrics", "data_quality",
)

CANDIDATE_METRIC_KEYS = (
    "selected_snapshot_at", "snapshot_gap_seconds", "previous_close_price", "open_price",
    "last_price", "amount", "volume", "stock_ret_prev_close_0935",
    "stock_ret_open_0935", "auction_ret_prev_close", "auction_amount",
    "auction_data_quality", "auction_data_quality_reason", "known_prev_trade_date",
    "known_prev_day_ret", "known_ret_3d", "known_ret_5d",
    "live_industry_strength_level", "live_industry_0935_breadth",
    "live_industry_0935_open_breadth", "live_industry_0935_avg_ret",
    "live_industry_0935_strong_3pct_count", "rank_pct_stock_ret_prev_close_0935",
    "rank_pct_stock_ret_open_0935", "rank_pct_stock_amount_0935",
    "rank_pct_live_industry_0935_avg_ret", "risk_penalty_known_ret_5d_ge_15pct",
    "risk_penalty_known_ret_5d_ge_20pct", "stock_rule_pass_live_safe_v0_1",
    "market_risk_level", "policy_suggestion", "candidate_scope", "candidate_role",
)
TIER_EVALUATION_METRIC_KEYS = (
    "candidate_price", "candidate_ret_prev_close", "execution_reference_price",
    "execution_ret_prev_close", "max_execution_price", "chase_risk_level",
    "chase_risk_reason", "stock_candidate_execution_ret", "industry_execution_up_ratio",
    "industry_execution_avg_ret_prev_close", "industry_execution_up_ratio_delta",
    "industry_execution_avg_ret_delta", "official_industry_execution_ret_prev_close",
    "official_industry_execution_ret_delta", "market_index_execution_sse_ret",
    "market_index_execution_zz1000_ret", "market_index_execution_avg_ret",
)


def build_generate_input(
    *,
    trade_date: date,
    previous_trade_date: date,
    cutoff_at: datetime,
    stock_quotes: pd.DataFrame,
    auctions: pd.DataFrame,
    daily_quotes: pd.DataFrame,
) -> OpeningCandidateGenerateInput:
    canonical_stock_quotes = _quote_frame(stock_quotes, GENERATE_STOCK_QUOTE_COLUMNS)
    canonical_auctions = _quote_frame(auctions, GENERATE_AUCTION_COLUMNS)
    if canonical_stock_quotes.empty:
        canonical_auctions = canonical_auctions.iloc[0:0].copy()
    else:
        symbols = set(canonical_stock_quotes["symbol"].dropna().astype(str))
        canonical_auctions = canonical_auctions[
            canonical_auctions["symbol"].astype(str).isin(symbols)
        ].reset_index(drop=True)
    return OpeningCandidateGenerateInput(
        trade_date=trade_date,
        previous_trade_date=previous_trade_date,
        cutoff_at=cutoff_at,
        stock_quotes=canonical_stock_quotes,
        auctions=canonical_auctions,
        daily_quotes=_quote_frame(daily_quotes, GENERATE_DAILY_COLUMNS),
    )


def candidate_handoff_from_output(output: OpeningCandidateGenerateOutput) -> pd.DataFrame:
    return candidate_handoff_from_frame(
        output.candidates,
        fallback_data_quality=output.data_quality,
    )


def candidate_handoff_from_frame(
    candidates: pd.DataFrame,
    *,
    fallback_data_quality: str,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for ordinal, row in enumerate(candidates.to_dict(orient="records"), start=1):
        quality = materialized_data_quality(
            (fallback_data_quality, row.get("auction_data_quality")),
        )
        rows.append(
            {
                "candidate_key": str(row["symbol"]),
                "trade_date": row.get("trade_date"),
                "asset_type": "stock",
                "asset_key": str(row["symbol"]),
                "asset_name": row.get("name"),
                "rank": int(row.get("candidate_rank_diversified_v0_1", ordinal)),
                "candidate_role": str(row.get("candidate_role") or "watch"),
                "score": none_float(row.get("candidate_score_live_industry_momentum_v0_1")),
                "metrics": {key: row.get(key) for key in CANDIDATE_METRIC_KEYS if key in row},
                "data_quality": quality,
            }
        )
    return canonical_candidate_handoff(pd.DataFrame(rows))


def canonical_candidate_handoff(frame: pd.DataFrame) -> pd.DataFrame:
    output = _project(frame, CANDIDATE_HANDOFF_COLUMNS)
    if output.empty:
        return output
    output["trade_date"] = pd.to_datetime(output["trade_date"]).dt.date
    output["rank"] = pd.to_numeric(output["rank"], errors="raise").astype(int)
    output["score"] = output["score"].map(_canonical_score)
    return output


def build_evaluation_input(
    *,
    trade_date: date,
    candidate_cutoff_at: datetime,
    evaluation_cutoff_at: datetime,
    candidates: pd.DataFrame,
    stock_quotes: pd.DataFrame,
    candidate_industries: pd.DataFrame,
    industry_members: pd.DataFrame,
    industry_quotes: pd.DataFrame,
    index_quotes: pd.DataFrame,
) -> CandidateEvaluationInput:
    return CandidateEvaluationInput(
        trade_date=trade_date,
        candidate_cutoff_at=candidate_cutoff_at,
        evaluation_cutoff_at=evaluation_cutoff_at,
        candidates=canonical_candidate_handoff(candidates),
        stock_quotes=_quote_frame(stock_quotes, EVALUATION_STOCK_QUOTE_COLUMNS),
        candidate_industries=_project(
            candidate_industries, ("symbol", "industry_symbol", "industry_name")
        ),
        industry_members=_project(industry_members, ("symbol", "industry_symbol")),
        industry_quotes=_quote_frame(
            industry_quotes, EVALUATION_INDUSTRY_QUOTE_COLUMNS
        ),
        index_quotes=_quote_frame(index_quotes, EVALUATION_INDEX_QUOTE_COLUMNS),
    )


def evaluation_handoff_from_output(output: CandidateEvaluationOutput) -> pd.DataFrame:
    return canonical_evaluation_handoff(output.evaluations)


def canonical_evaluation_handoff(frame: pd.DataFrame) -> pd.DataFrame:
    output = _project(frame, EVALUATION_HANDOFF_COLUMNS)
    if output.empty:
        return output
    output["score"] = output["score"].map(_canonical_score)
    output["metrics"] = output["metrics"].map(_tier_metrics)
    return output


def build_tier_input(
    *,
    trade_date: date,
    cutoff_at: datetime,
    candidates: pd.DataFrame,
    evaluations: pd.DataFrame,
) -> CandidateTierInput:
    return CandidateTierInput(
        trade_date=trade_date,
        cutoff_at=cutoff_at,
        candidates=canonical_candidate_handoff(candidates),
        evaluations=canonical_evaluation_handoff(evaluations),
    )


def _quote_frame(frame: pd.DataFrame, columns: tuple[str, ...]) -> pd.DataFrame:
    output = _project(frame, columns)
    if output.empty:
        return output
    if "trade_date" in output:
        output["trade_date"] = pd.to_datetime(output["trade_date"]).dt.date
    for column in ("snapshot_at", "quote_time", "observed_at"):
        if column in output:
            output[column] = pd.to_datetime(output[column])
    excluded = {
        "trade_date", "snapshot_at", "quote_time", "observed_at", "symbol", "name",
        "exchange", "market", "listing_status", "industry_symbol", "industry_name",
        "classification_system",
    }
    for column in output.columns:
        if column not in excluded:
            output[column] = pd.to_numeric(output[column], errors="coerce")
    return output


def _project(frame: pd.DataFrame, columns: tuple[str, ...]) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=columns)
    missing = [column for column in columns if column not in frame]
    if missing:
        raise ValueError(f"missing RuleInput columns: {', '.join(missing)}")
    return frame.loc[:, list(columns)].copy().reset_index(drop=True)


def _tier_metrics(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {key: value.get(key) for key in TIER_EVALUATION_METRIC_KEYS if key in value}


def _canonical_score(value: Any) -> float | None:
    number = none_float(value)
    return None if number is None else float(f"{number:.15g}")
