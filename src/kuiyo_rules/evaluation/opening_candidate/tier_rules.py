from __future__ import annotations

from typing import Any

import pandas as pd


WATCH_LEVEL_PRIORITY = {
    "focus_watch": 1,
    "secondary_watch": 2,
    "observe_only": 3,
    "reject": 4,
}


def apply_watch_tiers(features: pd.DataFrame) -> pd.DataFrame:
    if features.empty:
        return features
    output = features.copy()
    levels: list[str] = []
    reasons: list[tuple[str, ...]] = []
    for _, row in output.iterrows():
        level, row_reasons = tier_row(row)
        levels.append(level)
        reasons.append(tuple(row_reasons))
    output["watch_level"] = levels
    output["reasons"] = reasons
    output["priority"] = output["watch_level"].map(WATCH_LEVEL_PRIORITY).fillna(9).astype(int)
    output["data_quality"] = output.apply(row_data_quality, axis=1)
    output = output.sort_values(
        ["priority", "evaluation_score", "candidate_score", "rank"],
        ascending=[True, False, False, True],
    ).copy()
    output["priority"] = range(1, len(output) + 1)
    output["metrics"] = [tier_metrics(row) for row in output.to_dict(orient="records")]
    return output.sort_values("priority")


def tier_row(row: pd.Series) -> tuple[str, list[str]]:
    reasons: list[str] = []
    decision = clean_text(row.get("evaluation_decision"))
    timing = clean_text(row.get("live_timing_state"))
    chase = clean_text(row.get("chase_risk_level"))
    hard_tags = tags_by_kind(row.get("evaluation_tags"), "hard")
    soft_tags = tags_by_kind(row.get("evaluation_tags"), "soft")

    if clean_text(row.get("candidate_role")) == "shadow":
        return "observe_only", ["shadow_diagnostic_only"]
    if decision in {"reject", "invalid"} or hard_tags:
        return "reject", ["evaluation_reject_or_hard_tags"]
    if timing == "faded_before_execution":
        return "reject", ["price_faded_before_execution"]
    if timing in {"missing_live_timing", "missing_evaluation"}:
        return "observe_only", ["missing_or_incomplete_timing"]
    if timing == "already_hot_by_candidate_cutoff":
        return "observe_only", ["already_hot_by_candidate_cutoff_chase_risk"]
    if chase == "high":
        return "observe_only", ["high_chase_risk"]
    if (
        decision in {"strong_confirm", "confirm"}
        and timing in {"continued_after_candidate_cutoff", "stable_after_candidate_cutoff"}
        and chase in {"normal", ""}
    ):
        return "focus_watch", ["execution_confirmed_and_timing_held"]
    if decision in {"strong_confirm", "confirm", "weak_confirm"} and soft_tags:
        return "secondary_watch", ["has_soft_confirm_but_not_focus"]
    reasons.append("no_clear_confirmation")
    return "observe_only", reasons


def row_data_quality(row: pd.Series) -> str:
    qualities = [
        clean_text(row.get("candidate_data_quality"), "normal"),
        clean_text(row.get("evaluation_data_quality"), "normal"),
    ]
    for quality in ("missing", "degraded", "partial", "proxy", "stale"):
        if quality in qualities:
            return quality
    return "normal"


def tags_by_kind(tags: object, key: str) -> list[str]:
    if not isinstance(tags, dict):
        return []
    value = tags.get(key)
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    return []


def clean_text(value: object, default: str = "") -> str:
    if value is None:
        return default
    try:
        if pd.isna(value):
            return default
    except (TypeError, ValueError):
        pass
    text = str(value)
    return default if text.lower() == "nan" else text


def tier_metrics(row: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "asset_key",
        "asset_name",
        "rank",
        "candidate_role",
        "candidate_score",
        "evaluation_decision",
        "evaluation_score",
        "evaluation_tags",
        "live_timing_state",
        "candidate_price",
        "candidate_ret_prev_close",
        "execution_reference_price",
        "execution_ret_prev_close",
        "max_execution_price",
        "chase_risk_level",
        "chase_risk_reason",
        "stock_candidate_execution_ret",
        "industry_execution_up_ratio",
        "industry_execution_avg_ret_prev_close",
        "industry_execution_up_ratio_delta",
        "industry_execution_avg_ret_delta",
        "official_industry_execution_ret_prev_close",
        "official_industry_execution_ret_delta",
        "market_index_execution_sse_ret",
        "market_index_execution_zz1000_ret",
        "market_index_execution_avg_ret",
    ]
    return {key: row.get(key) for key in keys if key in row}
