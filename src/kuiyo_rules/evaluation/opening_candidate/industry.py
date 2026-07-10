from __future__ import annotations

import pandas as pd

from kuiyo_rules.evaluation.opening_candidate.parameters import OpeningCandidateGenerateParameters


STRENGTH_ORDER = {"none": 0, "moderate": 1, "strong": 2, "very_strong": 3}


def build_industry_stats(
    enriched: pd.DataFrame,
    *,
    parameters: OpeningCandidateGenerateParameters,
) -> pd.DataFrame:
    if enriched.empty:
        return pd.DataFrame()
    stats = (
        enriched.groupby(["trade_date", "industry_symbol", "industry_name"], dropna=False)
        .agg(
            live_industry_members=("symbol", "nunique"),
            live_industry_0935_breadth=("stock_ret_prev_close_0935", lambda values: float((values > 0).mean())),
            live_industry_0935_open_breadth=("stock_ret_open_0935", lambda values: float((values > 0).mean())),
            live_industry_0935_avg_ret=("stock_ret_prev_close_0935", "mean"),
            live_industry_0935_strong_3pct_count=(
                "stock_ret_prev_close_0935",
                lambda values: int((values >= 0.03).sum()),
            ),
            live_industry_0935_strong_5pct_count=(
                "stock_ret_prev_close_0935",
                lambda values: int((values >= 0.05).sum()),
            ),
            live_industry_turnover_amount_yuan=("amount", "sum"),
        )
        .reset_index()
    )
    stats = stats[stats["live_industry_members"] >= parameters.minimum_industry_members].copy()
    if stats.empty:
        return stats
    stats["classification_system"] = parameters.classification_system
    stats["live_industry_strength_level"] = stats.apply(
        lambda row: live_industry_strength_level(row, parameters=parameters),
        axis=1,
    )
    stats["live_industry_strength_order"] = (
        stats["live_industry_strength_level"].map(STRENGTH_ORDER).fillna(0).astype(int)
    )
    return stats


def live_industry_strength_level(
    row: pd.Series,
    *,
    parameters: OpeningCandidateGenerateParameters,
) -> str:
    breadth = row["live_industry_0935_breadth"]
    average_return = row["live_industry_0935_avg_ret"]
    strong_count = row["live_industry_0935_strong_3pct_count"]
    if (
        breadth >= parameters.very_strong_industry_breadth
        and average_return >= parameters.very_strong_industry_average_return
        and strong_count >= parameters.very_strong_industry_minimum_3pct_count
    ):
        return "very_strong"
    if breadth >= parameters.strong_industry_breadth and average_return >= parameters.strong_industry_average_return:
        return "strong"
    if (
        breadth >= parameters.moderate_industry_breadth
        and average_return >= parameters.moderate_industry_average_return
    ):
        return "moderate"
    return "none"
