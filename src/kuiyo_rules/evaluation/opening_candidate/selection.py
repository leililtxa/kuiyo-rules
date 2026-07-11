from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from kuiyo_rules.evaluation.opening_candidate.parameters import OpeningCandidateGenerateParameters


@dataclass(frozen=True)
class RankedPoolEvaluation:
    ranked_pool: pd.DataFrame
    trace_rows: pd.DataFrame


def select_industries(
    *,
    industry_stats: pd.DataFrame,
    market_policy: dict[str, Any],
    parameters: OpeningCandidateGenerateParameters,
) -> pd.DataFrame:
    if industry_stats.empty:
        return industry_stats
    allowed = industry_stats.copy()
    suggestion = str(market_policy.get("policy_suggestion", "unknown"))
    if suggestion == "restricted_observation":
        allowed = allowed[allowed["live_industry_strength_level"].isin(["strong", "very_strong"])].copy()
        limit = parameters.restricted_industry_limit
    elif suggestion == "normal_observation":
        allowed = allowed[
            allowed["live_industry_strength_level"].isin(["moderate", "strong", "very_strong"])
        ].copy()
        limit = parameters.normal_industry_limit
    else:
        return allowed.iloc[0:0].copy()
    allowed = allowed.sort_values(
        [
            "live_industry_strength_order",
            "live_industry_0935_avg_ret",
            "live_industry_0935_breadth",
            "live_industry_members",
        ],
        ascending=[False, False, False, False],
    ).copy()
    allowed["market_risk_level"] = market_policy.get("market_risk_level")
    allowed["policy_suggestion"] = suggestion
    allowed["candidate_scope"] = suggestion
    allowed["candidate_role"] = "watch"
    allowed["context_role"] = "selected_signal"
    allowed["selected_live_industry_rank_v0_1"] = range(1, len(allowed) + 1)
    allowed["industry_selection_limit"] = limit
    return allowed[allowed["selected_live_industry_rank_v0_1"] <= limit].copy()


def select_shadow_industries(
    *,
    industry_stats: pd.DataFrame,
    market_policy: dict[str, Any],
    parameters: OpeningCandidateGenerateParameters,
) -> pd.DataFrame:
    if not should_generate_shadow_candidates(market_policy):
        return industry_stats.iloc[0:0].copy()
    allowed = industry_stats[industry_stats["live_industry_strength_level"].eq("moderate")].copy()
    if allowed.empty:
        return allowed
    allowed = allowed.sort_values(
        [
            "live_industry_strength_order",
            "live_industry_0935_avg_ret",
            "live_industry_0935_breadth",
            "live_industry_members",
        ],
        ascending=[False, False, False, False],
    ).copy()
    allowed["market_risk_level"] = market_policy.get("market_risk_level")
    allowed["policy_suggestion"] = market_policy.get("policy_suggestion")
    allowed["candidate_scope"] = "weak_market_moderate_industry_shadow"
    allowed["candidate_role"] = "shadow"
    allowed["context_role"] = "diagnostic"
    allowed["selected_live_industry_rank_v0_1"] = range(1, len(allowed) + 1)
    allowed["industry_selection_limit"] = parameters.shadow_industry_limit
    return allowed[
        allowed["selected_live_industry_rank_v0_1"] <= parameters.shadow_industry_limit
    ].copy()


def should_generate_shadow_candidates(market_policy: dict[str, Any]) -> bool:
    return (
        market_policy.get("market_risk_level") == "weak"
        and market_policy.get("policy_suggestion") == "no_trade"
        and market_policy.get("best_live_industry_strength_level") == "moderate"
    )


def build_ranked_pool(
    *,
    enriched: pd.DataFrame,
    selected_industries: pd.DataFrame,
    parameters: OpeningCandidateGenerateParameters,
) -> pd.DataFrame:
    return evaluate_ranked_pool(
        enriched=enriched,
        selected_industries=selected_industries,
        parameters=parameters,
    ).ranked_pool


def evaluate_ranked_pool(
    *,
    enriched: pd.DataFrame,
    selected_industries: pd.DataFrame,
    parameters: OpeningCandidateGenerateParameters,
) -> RankedPoolEvaluation:
    if enriched.empty or selected_industries.empty:
        return RankedPoolEvaluation(ranked_pool=pd.DataFrame(), trace_rows=pd.DataFrame())
    pool = enriched.merge(
        selected_industries[
            [
                "industry_symbol",
                "industry_name",
                "selected_live_industry_rank_v0_1",
                "industry_selection_limit",
                "live_industry_strength_level",
                "live_industry_strength_order",
                "live_industry_0935_breadth",
                "live_industry_0935_open_breadth",
                "live_industry_0935_avg_ret",
                "live_industry_0935_strong_3pct_count",
                "market_risk_level",
                "policy_suggestion",
                "candidate_scope",
                "candidate_role",
                "context_role",
            ]
        ],
        on=["industry_symbol", "industry_name"],
        how="inner",
    )
    pool = add_basic_filters(pool, parameters=parameters)
    basic_failed = pool[~pool["candidate_basic_filter_pass"]].copy()
    eligible = pool[pool["candidate_basic_filter_pass"]].copy()
    if eligible.empty:
        return RankedPoolEvaluation(ranked_pool=eligible, trace_rows=basic_failed)
    eligible = add_rank_features(eligible, parameters=parameters)
    eligible = add_stock_rules(eligible, parameters=parameters)
    trace_rows = pd.concat([basic_failed, eligible], ignore_index=True, sort=False)
    return RankedPoolEvaluation(ranked_pool=eligible, trace_rows=trace_rows)


def add_basic_filters(
    pool: pd.DataFrame,
    *,
    parameters: OpeningCandidateGenerateParameters,
) -> pd.DataFrame:
    out = pool.copy()
    out["filter_exclude_st_name"] = out["name"].astype("string").str.contains("ST", case=False, na=False)
    out["filter_exclude_bj_market"] = out["market"].astype("string").str.upper().eq("BJ") | out[
        "exchange"
    ].astype("string").str.upper().eq("BJ")
    out["filter_exclude_non_active_listing"] = ~out["listing_status"].astype("string").eq("listed")
    out["filter_exclude_price_invalid"] = (
        out["previous_close_price"].isna()
        | out["open_price"].isna()
        | out["last_price"].isna()
        | (out["previous_close_price"] <= 0)
        | (out["open_price"] <= 0)
        | (out["last_price"] <= 0)
    )
    out["filter_exclude_limit_like_at_0935"] = (
        out["stock_ret_prev_close_0935"] >= parameters.limit_like_return
    )
    out["candidate_basic_filter_pass"] = ~(
        out["filter_exclude_st_name"]
        | out["filter_exclude_bj_market"]
        | out["filter_exclude_non_active_listing"]
        | out["filter_exclude_price_invalid"]
        | out["filter_exclude_limit_like_at_0935"]
    )
    return out


def add_rank_features(
    pool: pd.DataFrame,
    *,
    parameters: OpeningCandidateGenerateParameters,
) -> pd.DataFrame:
    out = pool.copy()
    out["rank_pct_stock_ret_prev_close_0935"] = out["stock_ret_prev_close_0935"].rank(pct=True)
    out["rank_pct_stock_ret_open_0935"] = out["stock_ret_open_0935"].rank(pct=True)
    out["rank_pct_stock_amount_0935"] = out["amount"].rank(pct=True)
    out["rank_pct_live_industry_0935_avg_ret"] = out["live_industry_0935_avg_ret"].rank(pct=True)
    overheat = pd.to_numeric(out["known_ret_5d"], errors="coerce").fillna(0.0)
    out["risk_penalty_known_ret_5d_ge_15pct"] = (
        overheat >= parameters.known_5d_penalty_first_threshold
    ).astype(int)
    out["risk_penalty_known_ret_5d_ge_20pct"] = (
        overheat >= parameters.known_5d_penalty_second_threshold
    ).astype(int)
    out["candidate_score_live_industry_momentum_v0_1"] = (
        parameters.industry_return_weight * out["rank_pct_live_industry_0935_avg_ret"].fillna(0.0)
        + parameters.stock_return_weight * out["rank_pct_stock_ret_prev_close_0935"].fillna(0.0)
        + parameters.stock_open_return_weight * out["rank_pct_stock_ret_open_0935"].fillna(0.0)
        + parameters.stock_amount_weight * out["rank_pct_stock_amount_0935"].fillna(0.0)
        - parameters.known_5d_penalty_weight * out["risk_penalty_known_ret_5d_ge_15pct"]
        - parameters.known_5d_penalty_weight * out["risk_penalty_known_ret_5d_ge_20pct"]
    )
    return out


def add_stock_rules(
    pool: pd.DataFrame,
    *,
    parameters: OpeningCandidateGenerateParameters,
) -> pd.DataFrame:
    out = pool.copy()
    out["stock_rule_pass_ret_prev_close_0935_gt_0"] = (
        out["stock_ret_prev_close_0935"] > parameters.minimum_return_previous_close
    )
    out["stock_rule_pass_ret_open_0935_ge_0"] = (
        out["stock_ret_open_0935"] >= parameters.minimum_return_open
    )
    out["stock_rule_pass_known_ret_5d_lt_15pct"] = out["known_ret_5d"].notna() & (
        out["known_ret_5d"] < parameters.known_5d_max
    )
    out["stock_rule_pass_known_ret_3d_gt_m8pct"] = out["known_ret_3d"].notna() & (
        out["known_ret_3d"] > parameters.known_3d_min
    )
    out["stock_rule_pass_prev_day_ret_gt_m7pct"] = out["known_prev_day_ret"].notna() & (
        out["known_prev_day_ret"] > parameters.previous_day_min
    )
    out["stock_rule_pass_auction_not_deep_gap_down"] = out["auction_ret_prev_close"].notna() & (
        out["auction_ret_prev_close"] > parameters.auction_return_min
    )
    out["stock_rule_pass_live_safe_v0_1"] = (
        out["stock_rule_pass_ret_prev_close_0935_gt_0"]
        & out["stock_rule_pass_ret_open_0935_ge_0"]
        & out["stock_rule_pass_known_ret_5d_lt_15pct"]
        & out["stock_rule_pass_known_ret_3d_gt_m8pct"]
        & out["stock_rule_pass_prev_day_ret_gt_m7pct"]
        & out["stock_rule_pass_auction_not_deep_gap_down"]
    )
    return out


def diversify_candidates(
    pool: pd.DataFrame,
    *,
    parameters: OpeningCandidateGenerateParameters,
) -> pd.DataFrame:
    if pool.empty:
        return pool
    out = pool[pool["stock_rule_pass_live_safe_v0_1"]].copy()
    if out.empty:
        return out
    out = out.sort_values(
        [
            "selected_live_industry_rank_v0_1",
            "candidate_score_live_industry_momentum_v0_1",
            "stock_ret_prev_close_0935",
            "amount",
        ],
        ascending=[True, False, False, False],
    )
    out["candidate_rank_within_live_industry_v0_1"] = out.groupby("industry_symbol", sort=False).cumcount() + 1
    out = out[
        out["candidate_rank_within_live_industry_v0_1"] <= parameters.maximum_stocks_per_industry
    ].copy()
    out = out.sort_values(
        ["selected_live_industry_rank_v0_1", "candidate_rank_within_live_industry_v0_1"],
        ascending=[True, True],
    )
    out["candidate_rank_diversified_v0_1"] = range(1, len(out) + 1)
    out["candidate_role"] = out.get("candidate_role", "watch")
    out["candidate_key"] = out["symbol"].astype(str)
    return out
