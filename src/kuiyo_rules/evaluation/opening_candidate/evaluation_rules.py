from __future__ import annotations

from typing import Any

import pandas as pd

from kuiyo_rules.evaluation.opening_candidate.parameters import CandidateEvaluationParameters
from kuiyo_rules.numeric import (
    missing,
    none_float,
    none_if_missing,
    number_ge,
    number_gt,
    number_le,
    number_lt,
)


def apply_execution_confirmation(
    features: pd.DataFrame,
    *,
    parameters: CandidateEvaluationParameters,
) -> pd.DataFrame:
    if features.empty:
        return features
    output = features.copy()
    hard_tags: list[list[str]] = []
    soft_tags: list[list[str]] = []
    decisions: list[str] = []
    for _, row in output.iterrows():
        hard, soft, decision = tag_row(row, parameters=parameters)
        hard_tags.append(hard)
        soft_tags.append(soft)
        decisions.append(decision)
    output["hard_tags"] = hard_tags
    output["soft_tags"] = soft_tags
    output["tags"] = [
        {"hard": hard, "soft": soft}
        for hard, soft in zip(hard_tags, soft_tags, strict=True)
    ]
    output["decision"] = decisions
    output["hard_tag_count"] = [len(item) for item in hard_tags]
    output["soft_tag_count"] = [len(item) for item in soft_tags]
    output["execution_score"] = output["soft_tag_count"] - output["hard_tag_count"] * 2
    output["score"] = output["execution_score"].astype(float)
    output["data_quality"] = output.apply(row_data_quality, axis=1)
    price_payloads = output.apply(
        lambda row: execution_price_payload(row, parameters=parameters),
        axis=1,
    )
    for key in price_payloads.iloc[0]:
        output[key] = [payload[key] for payload in price_payloads]
    output["metrics"] = [evaluation_metrics(row) for row in output.to_dict(orient="records")]
    return output


def tag_row(
    row: pd.Series,
    *,
    parameters: CandidateEvaluationParameters,
) -> tuple[list[str], list[str], str]:
    if missing(row.get("candidate_price")) or missing(row.get("execution_price")):
        return ["missing_stock_checkpoint"], [], "invalid"

    hard: list[str] = []
    soft: list[str] = []
    stock_move = row.get("stock_candidate_execution_ret")
    execution_ret_open = row.get("execution_ret_open")
    industry_up_delta = row.get("industry_execution_up_ratio_delta")
    industry_ret_delta = row.get("industry_execution_avg_ret_delta")
    industry_strong_delta = row.get("industry_execution_strong_3pct_delta")

    if number_le(stock_move, parameters.stock_fade):
        hard.append("hard_stock_fade_execution")
    if number_lt(execution_ret_open, 0):
        hard.append("hard_below_open_execution")
    if number_le(industry_up_delta, parameters.industry_breadth_fade):
        hard.append("hard_industry_breadth_fade_execution")
    if number_le(industry_ret_delta, parameters.industry_return_fade):
        hard.append("hard_industry_return_fade_execution")

    if number_ge(stock_move, parameters.stock_continuation):
        soft.append("confirm_stock_continuation_execution")
    if number_ge(execution_ret_open, 0):
        soft.append("confirm_above_open_execution")
    if number_ge(industry_up_delta, 0):
        soft.append("confirm_industry_breadth_holds_execution")
    if number_ge(industry_ret_delta, 0):
        soft.append("confirm_industry_return_holds_execution")
    if number_gt(industry_strong_delta, 0):
        soft.append("confirm_industry_strong_count_expands")

    if row.get("candidate_role") == "shadow":
        soft.append("shadow_diagnostic_only")
        return hard, soft, "observe"
    if (
        parameters.critical_hard_tags.intersection(hard)
        or len(hard) >= parameters.minimum_hard_tags_to_reject
    ):
        return hard, soft, "reject"
    if not hard and len(soft) >= parameters.strong_confirm_soft_tags:
        return hard, soft, "strong_confirm"
    if not hard and len(soft) >= parameters.confirm_soft_tags:
        return hard, soft, "confirm"
    if not hard and len(soft) >= parameters.weak_confirm_soft_tags:
        return hard, soft, "weak_confirm"
    return hard, soft, "observe"


def row_data_quality(row: pd.Series) -> str:
    candidate_quality = str(row.get("candidate_data_quality") or "normal")
    if row.get("decision") == "invalid":
        return "missing"
    if missing(row.get("industry_execution_up_ratio")):
        return "partial"
    if candidate_quality in {"proxy", "stale", "partial", "missing", "degraded"}:
        return candidate_quality
    return "normal"


def execution_price_payload(
    row: pd.Series,
    *,
    parameters: CandidateEvaluationParameters,
) -> dict[str, Any]:
    premium = execution_premium(row.get("decision"), parameters=parameters)
    execution_price = row.get("execution_price")
    max_execution_price = None
    if premium is not None and not missing(execution_price):
        max_execution_price = float(execution_price) * (1.0 + premium)
    risk_level, risk_reason = chase_risk(
        row.get("execution_ret_prev_close"),
        parameters=parameters,
    )
    return {
        "candidate_price": row.get("candidate_price"),
        "candidate_ret_prev_close": row.get("candidate_ret_prev_close"),
        "execution_reference_price": execution_price,
        "execution_ret_prev_close": row.get("execution_ret_prev_close"),
        "max_execution_premium": premium,
        "max_execution_price": max_execution_price,
        "chase_risk_level": risk_level,
        "chase_risk_reason": risk_reason,
    }


def execution_premium(
    decision: object,
    *,
    parameters: CandidateEvaluationParameters,
) -> float | None:
    if decision == "strong_confirm":
        return parameters.strong_confirm_premium
    if decision == "confirm":
        return parameters.confirm_premium
    if decision == "weak_confirm":
        return parameters.weak_confirm_premium
    return None


def chase_risk(
    ret_prev_close: object,
    *,
    parameters: CandidateEvaluationParameters,
) -> tuple[str, str]:
    value = none_float(ret_prev_close)
    if value is None:
        return "unknown", "missing_ret_prev_close"
    if value >= parameters.high_chase:
        return "high", "ret_prev_close_ge_8pct"
    if value >= parameters.elevated_chase:
        return "elevated", "ret_prev_close_ge_5pct"
    return "normal", "ret_prev_close_lt_5pct"


def evaluation_metrics(row: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "rank",
        "candidate_role",
        "candidate_score",
        "candidate_snapshot_at",
        "candidate_price",
        "candidate_ret_prev_close",
        "candidate_ret_open",
        "candidate_volume_shares",
        "candidate_turnover_amount_yuan",
        "execution_snapshot_at",
        "execution_price",
        "execution_ret_prev_close",
        "execution_ret_open",
        "execution_volume_shares",
        "execution_turnover_amount_yuan",
        "stock_candidate_execution_ret",
        "industry_symbol",
        "industry_name",
        "industry_candidate_member_count",
        "industry_candidate_up_ratio",
        "industry_candidate_avg_ret_prev_close",
        "industry_candidate_avg_ret_open",
        "industry_candidate_strong_3pct_count",
        "industry_execution_member_count",
        "industry_execution_up_ratio",
        "industry_execution_avg_ret_prev_close",
        "industry_execution_avg_ret_open",
        "industry_execution_strong_3pct_count",
        "industry_execution_up_ratio_delta",
        "industry_execution_avg_ret_delta",
        "industry_execution_strong_3pct_delta",
        "official_industry_candidate_snapshot_at",
        "official_industry_candidate_ret_prev_close",
        "official_industry_candidate_ret_open",
        "official_industry_execution_snapshot_at",
        "official_industry_execution_ret_prev_close",
        "official_industry_execution_ret_open",
        "official_industry_execution_ret_delta",
        "hard_tag_count",
        "soft_tag_count",
        "execution_reference_price",
        "max_execution_premium",
        "max_execution_price",
        "chase_risk_level",
        "chase_risk_reason",
    ]
    payload = {key: none_if_missing(row.get(key)) for key in keys if key in row}
    for key, value in row.items():
        if str(key).startswith("market_index_"):
            payload[str(key)] = none_if_missing(value)
    return payload
