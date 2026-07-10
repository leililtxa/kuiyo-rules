from __future__ import annotations

from typing import Any

import pandas as pd

from kuiyo_rules.evaluation.opening_candidate.parameters import CandidateTierParameters
from kuiyo_rules.numeric import none_float


def build_watch_tier_features(
    *,
    candidates: pd.DataFrame,
    evaluations: pd.DataFrame,
    parameters: CandidateTierParameters,
) -> pd.DataFrame:
    if candidates.empty:
        return pd.DataFrame()
    require_candidate_key(candidates)
    if not evaluations.empty:
        require_candidate_key(evaluations)
    evaluation_by_candidate = {
        str(row["candidate_key"]): row
        for row in evaluations.to_dict(orient="records")
    }
    rows: list[dict[str, Any]] = []
    for candidate in candidates.to_dict(orient="records"):
        candidate_key = str(candidate["candidate_key"])
        evaluation = evaluation_by_candidate.get(candidate_key)
        if evaluation is None:
            rows.append(missing_evaluation_row(candidate))
            continue
        row = {
            "candidate_key": candidate_key,
            "trade_date": candidate.get("trade_date"),
            "asset_key": candidate.get("asset_key"),
            "asset_name": candidate.get("asset_name"),
            "rank": candidate.get("rank"),
            "candidate_role": candidate.get("candidate_role"),
            "candidate_score": candidate.get("score"),
            "candidate_metrics": candidate.get("metrics", {}),
            "candidate_data_quality": candidate.get("data_quality", "normal"),
            "evaluation_decision": evaluation.get("decision"),
            "evaluation_score": evaluation.get("score"),
            "evaluation_tags": evaluation.get("tags", {}),
            "evaluation_metrics": evaluation.get("metrics", {}),
            "evaluation_data_quality": evaluation.get("data_quality", "normal"),
        }
        row.update(flatten_evaluation_metrics(row["evaluation_metrics"]))
        row["live_timing_state"] = live_timing_state(row, parameters=parameters)
        rows.append(row)
    return pd.DataFrame(rows)


def missing_evaluation_row(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "candidate_key": str(candidate["candidate_key"]),
        "trade_date": candidate.get("trade_date"),
        "asset_key": candidate.get("asset_key"),
        "asset_name": candidate.get("asset_name"),
        "rank": candidate.get("rank"),
        "candidate_role": candidate.get("candidate_role"),
        "candidate_score": candidate.get("score"),
        "candidate_metrics": candidate.get("metrics", {}),
        "candidate_data_quality": candidate.get("data_quality", "normal"),
        "evaluation_decision": "missing_evaluation",
        "evaluation_score": None,
        "evaluation_tags": {},
        "evaluation_metrics": {},
        "evaluation_data_quality": "missing",
        "live_timing_state": "missing_evaluation",
    }


def flatten_evaluation_metrics(metrics: object) -> dict[str, Any]:
    if not isinstance(metrics, dict):
        return {}
    keys = [
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
    return {key: metrics.get(key) for key in keys if key in metrics}


def live_timing_state(
    row: dict[str, Any],
    *,
    parameters: CandidateTierParameters,
) -> str:
    candidate_return = none_float(row.get("candidate_ret_prev_close"))
    move = none_float(row.get("stock_candidate_execution_ret"))
    if row.get("evaluation_decision") == "missing_evaluation":
        return "missing_evaluation"
    if (
        none_float(row.get("candidate_price")) is None
        or none_float(row.get("execution_reference_price")) is None
    ):
        return "missing_live_timing"
    if move is not None and move < parameters.faded_before_execution:
        return "faded_before_execution"
    if candidate_return is not None and candidate_return >= parameters.already_hot:
        return "already_hot_by_candidate_cutoff"
    if move is not None and move >= parameters.continued_after_candidate:
        return "continued_after_candidate_cutoff"
    if move is not None and move >= parameters.stable_after_candidate:
        return "stable_after_candidate_cutoff"
    return "weak_drift_before_execution"


def require_candidate_key(frame: pd.DataFrame) -> None:
    if "candidate_key" not in frame:
        raise ValueError("missing candidate columns: candidate_key")
