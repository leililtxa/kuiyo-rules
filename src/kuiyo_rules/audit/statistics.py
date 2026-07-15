from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pandas as pd


STANDARD_QUANTILES = (
    ("p05", 0.05),
    ("p10", 0.10),
    ("p25", 0.25),
    ("p50", 0.50),
    ("p75", 0.75),
    ("p90", 0.90),
    ("p95", 0.95),
)


def summarize_outcomes(
    frame: pd.DataFrame,
    *,
    outcome_columns: Iterable[str],
    group_columns: Iterable[str] = (),
) -> pd.DataFrame:
    groups = tuple(group_columns)
    outcomes = tuple(outcome_columns)
    required = ("trade_date", *groups, *outcomes)
    missing = [column for column in required if column not in frame]
    if missing:
        raise ValueError(f"missing audit outcome columns: {missing}")
    grouped = frame.groupby(list(groups), dropna=False, sort=True) if groups else [((), frame)]
    rows: list[dict[str, object]] = []
    for group_value, part in grouped:
        values = group_value if isinstance(group_value, tuple) else (group_value,)
        row: dict[str, object] = dict(zip(groups, values, strict=True))
        row["candidate_count"] = int(len(part))
        row["day_count"] = int(part["trade_date"].nunique())
        row["sample_level"] = sample_level(row["day_count"])
        for column in outcomes:
            numeric = pd.to_numeric(part[column], errors="coerce").dropna()
            row[f"{column}_count"] = int(numeric.size)
            row[f"{column}_mean"] = _number(numeric.mean())
            for name, quantile in STANDARD_QUANTILES:
                row[f"{column}_{name}"] = _number(numeric.quantile(quantile))
            row[f"{column}_win_rate"] = _rate(numeric > 0)
            row[f"{column}_loss_rate"] = _rate(numeric < 0)
            row[f"{column}_big_loss_rate_le_m3pct"] = _rate(numeric <= -0.03)
            row[f"{column}_big_loss_rate_le_m5pct"] = _rate(numeric <= -0.05)
            row[f"{column}_big_win_rate_ge_3pct"] = _rate(numeric >= 0.03)
            row[f"{column}_big_win_rate_ge_5pct"] = _rate(numeric >= 0.05)
        rows.append(row)
    return pd.DataFrame(rows)


def compare_rule_versions(
    baseline: pd.DataFrame,
    challenger: pd.DataFrame,
    *,
    outcome_column: str,
) -> pd.DataFrame:
    required = {"trade_date", "candidate_key", outcome_column}
    for name, frame in (("baseline", baseline), ("challenger", challenger)):
        missing = sorted(required.difference(frame.columns))
        if missing:
            raise ValueError(f"{name} missing comparison columns: {missing}")
    rows: list[dict[str, object]] = []
    for trade_date in sorted(set(baseline["trade_date"]).union(challenger["trade_date"])):
        left = baseline[baseline["trade_date"] == trade_date]
        right = challenger[challenger["trade_date"] == trade_date]
        left_keys = set(left["candidate_key"].astype(str))
        right_keys = set(right["candidate_key"].astype(str))
        union = left_keys | right_keys
        left_value = pd.to_numeric(left[outcome_column], errors="coerce").mean()
        right_value = pd.to_numeric(right[outcome_column], errors="coerce").mean()
        rows.append(
            {
                "trade_date": trade_date,
                "baseline_candidate_count": len(left_keys),
                "challenger_candidate_count": len(right_keys),
                "retained_count": len(left_keys & right_keys),
                "added_count": len(right_keys - left_keys),
                "dropped_count": len(left_keys - right_keys),
                "candidate_jaccard": len(left_keys & right_keys) / len(union) if union else 1.0,
                "baseline_basket_outcome": _number(left_value),
                "challenger_basket_outcome": _number(right_value),
                "paired_outcome_delta": _number(right_value - left_value),
                "no_candidate_disagreement": bool(left.empty) != bool(right.empty),
            }
        )
    return pd.DataFrame(rows)


def cluster_bootstrap_interval(
    frame: pd.DataFrame,
    *,
    value_column: str,
    cluster_column: str = "trade_date",
    iterations: int = 2_000,
    confidence: float = 0.95,
    seed: int = 0,
) -> tuple[float, float] | None:
    data = frame[[cluster_column, value_column]].dropna()
    clusters = data[cluster_column].drop_duplicates().to_numpy()
    if len(clusters) < 2:
        return None
    if iterations <= 0 or not 0 < confidence < 1:
        raise ValueError("invalid bootstrap configuration")
    rng = np.random.default_rng(seed)
    means: list[float] = []
    for _ in range(iterations):
        sampled = rng.choice(clusters, size=len(clusters), replace=True)
        values = pd.concat(
            [data.loc[data[cluster_column].eq(cluster), value_column] for cluster in sampled],
            ignore_index=True,
        )
        means.append(float(pd.to_numeric(values, errors="coerce").mean()))
    alpha = (1.0 - confidence) / 2.0
    return float(np.quantile(means, alpha)), float(np.quantile(means, 1.0 - alpha))


def sample_level(day_count: int) -> str:
    if day_count < 20:
        return "insufficient"
    if day_count < 60:
        return "limited"
    if day_count < 100:
        return "moderate"
    return "sufficient"


def _rate(values: pd.Series) -> float | None:
    valid = values.dropna()
    return _number(valid.mean()) if not valid.empty else None


def _number(value: object) -> float | None:
    return None if pd.isna(value) else float(value)

