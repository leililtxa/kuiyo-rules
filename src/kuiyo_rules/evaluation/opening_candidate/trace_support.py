from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

import pandas as pd

from kuiyo_rules.clauses import ClauseTrace, TraceEvaluationStatus
from kuiyo_rules.definitions import ResearchRuleVersion


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
