from __future__ import annotations

from datetime import date, datetime
from typing import Any

import pandas as pd

from kuiyo_rules.evaluation.opening_candidate.parameters import OpeningCandidateGenerateParameters
from kuiyo_rules.quality import aggregate_data_quality


def build_market_policy(
    *,
    trade_date: date,
    previous_trade_date: date,
    cutoff_at: datetime,
    daily_quotes: pd.DataFrame,
    industry_stats: pd.DataFrame,
    snapshot_at: datetime,
    snapshot_gap_seconds: float,
    parameters: OpeningCandidateGenerateParameters,
) -> dict[str, Any]:
    snapshot_quality = "ok" if snapshot_gap_seconds <= parameters.snapshot_max_gap_seconds else "stale"
    previous_breadth = previous_market_breadth(
        daily_quotes=daily_quotes,
        previous_trade_date=previous_trade_date,
    )
    best = best_industry(industry_stats)
    policy = {
        "trade_date": trade_date.isoformat(),
        "previous_trading_date": previous_trade_date.isoformat(),
        "cutoff_at": cutoff_at.isoformat(),
        "selected_snapshot_at": pd.Timestamp(snapshot_at).isoformat(),
        "snapshot_quality": snapshot_quality,
        "snapshot_gap_seconds": snapshot_gap_seconds,
        "prev_market_breadth": previous_breadth,
        "market_risk_level": market_risk_level(previous_breadth, parameters=parameters),
        "best_live_industry": best.get("industry_symbol"),
        "best_live_industry_name": best.get("industry_name"),
        "best_live_industry_strength_level": best.get("live_industry_strength_level", "none"),
        "best_live_industry_0935_avg_ret": best.get("live_industry_0935_avg_ret"),
        "best_live_industry_0935_breadth": best.get("live_industry_0935_breadth"),
    }
    policy["policy_suggestion"] = policy_suggestion(policy)
    return policy


def previous_market_breadth(*, daily_quotes: pd.DataFrame, previous_trade_date: date) -> float | None:
    if daily_quotes.empty:
        return None
    previous = daily_quotes[daily_quotes["trade_date"] == previous_trade_date]
    if previous.empty:
        return None
    return float((previous["day_ret"] > 0).mean())


def best_industry(industry_stats: pd.DataFrame) -> dict[str, Any]:
    if industry_stats.empty:
        return {}
    sorted_stats = industry_stats.sort_values(
        ["live_industry_strength_order", "live_industry_0935_avg_ret", "live_industry_0935_breadth"],
        ascending=[False, False, False],
    )
    return dict(sorted_stats.iloc[0])


def market_risk_level(
    previous_breadth: float | None,
    *,
    parameters: OpeningCandidateGenerateParameters,
) -> str:
    if previous_breadth is None or pd.isna(previous_breadth):
        return "unknown"
    if previous_breadth < parameters.weak_market_breadth:
        return "weak"
    if previous_breadth < parameters.strong_market_breadth:
        return "neutral"
    return "strong"


def policy_suggestion(policy: dict[str, Any]) -> str:
    if policy["snapshot_quality"] != "ok":
        return "data_gap_observe_only"
    if policy["market_risk_level"] == "weak":
        if policy["best_live_industry_strength_level"] in {"very_strong", "strong"}:
            return "restricted_observation"
        return "no_trade"
    if policy["market_risk_level"] == "neutral":
        if policy["best_live_industry_strength_level"] in {"very_strong", "strong"}:
            return "normal_observation"
        if policy["best_live_industry_strength_level"] == "moderate":
            return "restricted_observation"
        return "no_trade"
    if policy["market_risk_level"] == "strong":
        return "normal_observation"
    return "unknown"


def result_data_quality(
    *,
    selected: pd.DataFrame,
    market_policy: dict[str, Any],
    daily_quotes: pd.DataFrame,
) -> str:
    if daily_quotes.empty:
        return "missing"
    if market_policy.get("snapshot_quality") != "ok":
        return "degraded"
    if selected.empty:
        return "normal"
    quality = aggregate_data_quality(selected["auction_data_quality"].tolist())
    return "partial" if quality == "missing" else quality


def missing_market_policy(reason: str) -> dict[str, Any]:
    return {
        "snapshot_quality": "missing",
        "market_risk_level": "unknown",
        "policy_suggestion": "no_trade",
        "reason": reason,
    }


def missing_previous_daily_market_policy(
    *,
    trade_date: date,
    previous_trade_date: date,
    cutoff_at: datetime,
    snapshot_at: datetime,
    snapshot_gap_seconds: float,
    parameters: OpeningCandidateGenerateParameters,
) -> dict[str, Any]:
    snapshot_quality = "ok" if snapshot_gap_seconds <= parameters.snapshot_max_gap_seconds else "stale"
    return {
        "trade_date": trade_date.isoformat(),
        "previous_trading_date": previous_trade_date.isoformat(),
        "cutoff_at": cutoff_at.isoformat(),
        "selected_snapshot_at": pd.Timestamp(snapshot_at).isoformat(),
        "snapshot_quality": snapshot_quality,
        "snapshot_gap_seconds": snapshot_gap_seconds,
        "prev_market_breadth": None,
        "market_risk_level": "unknown",
        "policy_suggestion": "data_gap_observe_only",
        "reason": "missing_previous_daily_quotes",
    }

