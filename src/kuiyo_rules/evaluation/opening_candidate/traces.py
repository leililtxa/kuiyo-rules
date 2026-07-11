from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import Any

import pandas as pd

from kuiyo_rules.clauses import ClauseTrace, TraceEvaluationStatus
from kuiyo_rules.definitions import ResearchRuleVersion


def generate_clause_traces(
    *,
    rule_version: ResearchRuleVersion,
    cutoff_at: datetime,
    status: str,
    data_quality: str,
    market_policy: Mapping[str, Any],
    industry_stats: pd.DataFrame,
    selected_industries: pd.DataFrame,
    stock_trace_rows: pd.DataFrame,
) -> tuple[ClauseTrace, ...]:
    attempt_key = cutoff_at.isoformat()
    traces: list[ClauseTrace] = [
        make_trace(
            rule_version,
            clause_key="opening.market-policy",
            stage_key="generate",
            attempt_key=attempt_key,
            subject_type="market",
            subject_key="aggregate",
            evaluation_status="evaluated" if market_policy else "unavailable",
            inputs={
                "market_breadth": market_policy.get("market_breadth"),
                "best_industry_strength": market_policy.get("best_live_industry_strength_level"),
                "snapshot_gap_seconds": market_policy.get("snapshot_gap_seconds"),
            },
            output={
                "market_risk_level": market_policy.get("market_risk_level"),
                "policy_suggestion": market_policy.get("policy_suggestion"),
            },
            reason_codes=reason_codes(market_policy.get("reason")),
            data_quality=data_quality,
        )
    ]
    selected_keys = frame_keys(selected_industries, "industry_symbol")
    if industry_stats.empty:
        traces.append(
            make_trace(
                rule_version,
                clause_key="opening.industry-strength",
                stage_key="generate",
                attempt_key=attempt_key,
                subject_type="industry",
                subject_key="aggregate",
                evaluation_status="unavailable",
                inputs={},
                output={"selected": False},
                reason_codes=("industry_stats_unavailable",),
                data_quality=data_quality,
            )
        )
    else:
        for row in industry_stats.to_dict(orient="records"):
            industry_key = text(row.get("industry_symbol"), "unknown")
            traces.append(
                make_trace(
                    rule_version,
                    clause_key="opening.industry-strength",
                    stage_key="generate",
                    attempt_key=attempt_key,
                    subject_type="industry",
                    subject_key=industry_key,
                    evaluation_status="evaluated",
                    inputs=pick(
                        row,
                        "live_industry_members",
                        "live_industry_0935_breadth",
                        "live_industry_0935_avg_ret",
                        "live_industry_0935_strong_3pct_count",
                    ),
                    output={
                        "strength_level": row.get("live_industry_strength_level"),
                        "strength_order": row.get("live_industry_strength_order"),
                        "selected": industry_key in selected_keys,
                    },
                    reason_codes=("selected",) if industry_key in selected_keys else ("not_selected",),
                    data_quality=data_quality,
                )
            )
    traces.extend(stock_clause_traces(rule_version, attempt_key, stock_trace_rows, data_quality))
    traces.append(
        make_trace(
            rule_version,
            clause_key="opening.data-quality-guard",
            stage_key="generate",
            attempt_key=attempt_key,
            subject_type="stage",
            subject_key="generate",
            evaluation_status="evaluated",
            inputs={
                "snapshot_quality": market_policy.get("snapshot_quality"),
                "stock_subject_count": int(len(stock_trace_rows)),
            },
            output={"status": status, "data_quality": data_quality},
            reason_codes=quality_reasons(data_quality, market_policy.get("reason")),
            data_quality=data_quality,
        )
    )
    return tuple(traces)


def evaluation_clause_traces(
    *,
    rule_version: ResearchRuleVersion,
    cutoff_at: datetime,
    evaluations: pd.DataFrame,
    status: str,
    data_quality: str,
) -> tuple[ClauseTrace, ...]:
    attempt_key = cutoff_at.isoformat()
    traces: list[ClauseTrace] = []
    for row in evaluations.to_dict(orient="records"):
        subject_key = text(row.get("asset_key", row.get("symbol")), "unknown")
        traces.append(
            make_trace(
                rule_version,
                clause_key="opening.execution-confirmation",
                stage_key="evaluate",
                attempt_key=attempt_key,
                subject_type="candidate",
                subject_key=subject_key,
                evaluation_status="evaluated",
                inputs=pick(
                    row,
                    "stock_candidate_execution_ret",
                    "execution_ret_open",
                    "industry_execution_up_ratio_delta",
                    "industry_execution_avg_ret_delta",
                    "industry_execution_strong_3pct_delta",
                ),
                output=pick(
                    row,
                    "decision",
                    "hard_tags",
                    "soft_tags",
                    "execution_score",
                    "max_execution_premium",
                    "chase_risk_level",
                ),
                reason_codes=tuple(string_items(row.get("hard_tags")) + string_items(row.get("soft_tags"))),
                data_quality=text(row.get("data_quality"), data_quality),
            )
        )
    if not traces:
        traces.append(
            make_trace(
                rule_version,
                clause_key="opening.execution-confirmation",
                stage_key="evaluate",
                attempt_key=attempt_key,
                subject_type="candidate",
                subject_key="aggregate",
                evaluation_status="unavailable",
                inputs={},
                output={"status": status},
                reason_codes=("no_candidate_features",),
                data_quality=data_quality,
            )
        )
    traces.append(quality_trace(rule_version, "evaluate", attempt_key, status, data_quality))
    return tuple(traces)


def tier_clause_traces(
    *,
    rule_version: ResearchRuleVersion,
    cutoff_at: datetime,
    tiers: pd.DataFrame,
    status: str,
    data_quality: str,
) -> tuple[ClauseTrace, ...]:
    attempt_key = cutoff_at.isoformat()
    traces: list[ClauseTrace] = []
    for row in tiers.to_dict(orient="records"):
        subject_key = text(row.get("asset_key", row.get("symbol")), "unknown")
        reasons = tuple(string_items(row.get("reasons")))
        traces.append(
            make_trace(
                rule_version,
                clause_key="opening.watch-tier",
                stage_key="tier",
                attempt_key=attempt_key,
                subject_type="candidate",
                subject_key=subject_key,
                evaluation_status="evaluated",
                inputs=pick(
                    row,
                    "evaluation_decision",
                    "evaluation_score",
                    "candidate_score",
                    "live_timing_state",
                    "chase_risk_level",
                ),
                output=pick(row, "watch_level", "priority"),
                reason_codes=reasons,
                data_quality=text(row.get("data_quality"), data_quality),
            )
        )
    if not traces:
        traces.append(
            make_trace(
                rule_version,
                clause_key="opening.watch-tier",
                stage_key="tier",
                attempt_key=attempt_key,
                subject_type="candidate",
                subject_key="aggregate",
                evaluation_status="unavailable",
                inputs={},
                output={"status": status},
                reason_codes=("upstream_no_evaluation",),
                data_quality=data_quality,
            )
        )
    traces.append(quality_trace(rule_version, "tier", attempt_key, status, data_quality))
    return tuple(traces)


def stock_clause_traces(
    rule_version: ResearchRuleVersion,
    attempt_key: str,
    rows: pd.DataFrame,
    data_quality: str,
) -> list[ClauseTrace]:
    traces: list[ClauseTrace] = []
    for row in rows.to_dict(orient="records"):
        subject_key = text(row.get("symbol"), "unknown")
        basic_pass = truth(row.get("candidate_basic_filter_pass"))
        safety_pass = truth(row.get("stock_rule_pass_live_safe_v0_1")) if basic_pass else False
        eligibility_reasons = false_flag_names(
            row,
        )
        traces.append(
            make_trace(
                rule_version,
                clause_key="opening.stock-eligibility",
                stage_key="generate",
                attempt_key=attempt_key,
                subject_type="stock",
                subject_key=subject_key,
                evaluation_status="evaluated",
                inputs=pick(
                    row,
                    "stock_ret_prev_close_0935",
                    "stock_ret_open_0935",
                    "known_ret_5d",
                    "known_ret_3d",
                    "known_prev_day_ret",
                    "auction_ret_prev_close",
                ),
                output={"basic_pass": basic_pass, "safety_pass": safety_pass},
                reason_codes=eligibility_reasons or (("passed",) if basic_pass and safety_pass else ("not_evaluated",)),
                data_quality=text(row.get("auction_data_quality"), data_quality),
            )
        )
        scoring_available = "candidate_score_live_industry_momentum_v0_1" in row
        traces.append(
            make_trace(
                rule_version,
                clause_key="opening.candidate-scoring",
                stage_key="generate",
                attempt_key=attempt_key,
                subject_type="stock",
                subject_key=subject_key,
                evaluation_status="evaluated" if scoring_available else "skipped",
                inputs=pick(
                    row,
                    "rank_pct_live_industry_0935_avg_ret",
                    "rank_pct_stock_ret_prev_close_0935",
                    "rank_pct_stock_ret_open_0935",
                    "rank_pct_stock_amount_0935",
                    "known_ret_5d",
                ),
                output=pick(
                    row,
                    "candidate_score_live_industry_momentum_v0_1",
                    "risk_penalty_known_ret_5d_ge_15pct",
                    "risk_penalty_known_ret_5d_ge_20pct",
                ),
                reason_codes=("scored",) if scoring_available else ("basic_filter_failed",),
                data_quality=text(row.get("auction_data_quality"), data_quality),
            )
        )
    return traces


def quality_trace(
    rule_version: ResearchRuleVersion,
    stage_key: str,
    attempt_key: str,
    status: str,
    data_quality: str,
) -> ClauseTrace:
    return make_trace(
        rule_version,
        clause_key="opening.data-quality-guard",
        stage_key=stage_key,
        attempt_key=attempt_key,
        subject_type="stage",
        subject_key=stage_key,
        evaluation_status="evaluated",
        inputs={},
        output={"status": status, "data_quality": data_quality},
        reason_codes=quality_reasons(data_quality),
        data_quality=data_quality,
    )


def make_trace(
    rule_version: ResearchRuleVersion,
    *,
    clause_key: str,
    stage_key: str,
    attempt_key: str,
    subject_type: str,
    subject_key: str,
    evaluation_status: TraceEvaluationStatus,
    inputs: Mapping[str, Any],
    output: Mapping[str, Any],
    reason_codes: Iterable[str] = (),
    data_quality: str,
) -> ClauseTrace:
    clause_version = next(
        item.clause_version
        for item in rule_version.clause_composition
        if item.clause_key == clause_key
    )
    return ClauseTrace(
        clause_key=clause_key,
        clause_version=clause_version,
        stage_key=stage_key,
        attempt_key=attempt_key,
        subject_type=subject_type,
        subject_key=subject_key,
        evaluation_status=evaluation_status,
        inputs=clean_mapping(inputs),
        output=clean_mapping(output),
        reason_codes=tuple(reason_codes),
        data_quality=data_quality,
    )


def clean_mapping(values: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key): scalar(value) for key, value in values.items()}


def scalar(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): scalar(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [scalar(item) for item in value]
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item"):
        return scalar(value.item())
    return value


def pick(row: Mapping[str, Any], *keys: str) -> dict[str, Any]:
    return {key: row.get(key) for key in keys if key in row}


def text(value: Any, default: str) -> str:
    cleaned = scalar(value)
    return default if cleaned is None or str(cleaned) == "" else str(cleaned)


def truth(value: Any) -> bool:
    cleaned = scalar(value)
    return bool(cleaned) if cleaned is not None else False


def string_items(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if str(item)]
    return []


def frame_keys(frame: pd.DataFrame, column: str) -> set[str]:
    if frame.empty or column not in frame:
        return set()
    return set(frame[column].dropna().astype(str))


def reason_codes(value: Any) -> tuple[str, ...]:
    cleaned = scalar(value)
    return () if cleaned is None or str(cleaned) == "" else (str(cleaned),)


def quality_reasons(data_quality: str, extra: Any = None) -> tuple[str, ...]:
    reasons = list(reason_codes(extra))
    if data_quality != "normal":
        reasons.append(f"quality_{data_quality}")
    return tuple(dict.fromkeys(reasons))


def false_flag_names(row: Mapping[str, Any]) -> tuple[str, ...]:
    reasons: list[str] = []
    for key, value in row.items():
        name = str(key)
        if name.startswith("filter_exclude_") and truth(value):
            reasons.append(name)
        elif name.startswith("stock_rule_pass_") and name != "stock_rule_pass_live_safe_v0_1" and not truth(value):
            reasons.append(name.replace("stock_rule_pass_", "stock_rule_failed_"))
    return tuple(reasons)
