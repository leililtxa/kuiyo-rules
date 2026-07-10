from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd

from kuiyo_rules.numeric import none_float, ratio, safe_sub
from kuiyo_rules.time_series import latest_by_symbol_before, nearest_before


def build_execution_features(
    *,
    candidates: pd.DataFrame,
    stock_quotes: pd.DataFrame,
    candidate_industries: pd.DataFrame,
    industry_members: pd.DataFrame,
    industry_quotes: pd.DataFrame,
    index_quotes: pd.DataFrame,
    candidate_cutoff_at: datetime,
    execution_cutoff_at: datetime,
) -> pd.DataFrame:
    if candidates.empty:
        return pd.DataFrame()
    require_columns(candidates, "candidate_key", "asset_key")
    rows: list[dict[str, Any]] = []
    industry_by_symbol = industry_mapping(candidate_industries)
    industry_stats = build_industry_checkpoints(
        stock_quotes=stock_quotes,
        industry_members=industry_members,
        candidate_cutoff_at=candidate_cutoff_at,
        execution_cutoff_at=execution_cutoff_at,
    )
    official_industry_stats = build_official_industry_checkpoints(
        industry_quotes=industry_quotes,
        candidate_cutoff_at=candidate_cutoff_at,
        execution_cutoff_at=execution_cutoff_at,
    )
    index_stats = build_index_checkpoints(
        index_quotes=index_quotes,
        candidate_cutoff_at=candidate_cutoff_at,
        execution_cutoff_at=execution_cutoff_at,
    )
    for candidate in candidates.to_dict(orient="records"):
        asset_key = str(candidate["asset_key"])
        industry = industry_by_symbol.get(asset_key, {})
        stock_part = (
            stock_quotes[stock_quotes["symbol"].astype(str).eq(asset_key)]
            if not stock_quotes.empty
            else pd.DataFrame()
        )
        candidate_quote = nearest_before(stock_part, candidate_cutoff_at)
        execution_quote = nearest_before(stock_part, execution_cutoff_at)
        row: dict[str, Any] = {
            "candidate_key": str(candidate["candidate_key"]),
            "trade_date": candidate.get("trade_date"),
            "asset_type": candidate.get("asset_type"),
            "asset_key": asset_key,
            "asset_name": candidate.get("asset_name"),
            "rank": candidate.get("rank"),
            "candidate_role": candidate.get("candidate_role"),
            "candidate_score": candidate.get("score"),
            "candidate_metrics": candidate.get("metrics", {}),
            "candidate_data_quality": candidate.get("data_quality", "normal"),
            "industry_symbol": industry.get("industry_symbol"),
            "industry_name": industry.get("industry_name"),
        }
        row.update(stock_checkpoint_features("candidate", candidate_quote))
        row.update(stock_checkpoint_features("execution", execution_quote))
        row["stock_candidate_execution_ret"] = ratio(
            row.get("execution_price"),
            row.get("candidate_price"),
        )
        industry_symbol = row.get("industry_symbol")
        if industry_symbol in industry_stats:
            row.update(industry_stats[industry_symbol])
        if industry_symbol in official_industry_stats:
            row.update(official_industry_stats[industry_symbol])
        row.update(index_stats)
        rows.append(row)
    return pd.DataFrame(rows)


def industry_mapping(candidate_industries: pd.DataFrame) -> dict[str, dict[str, Any]]:
    if candidate_industries.empty:
        return {}
    return {
        str(row["symbol"]): {
            "industry_symbol": row.get("industry_symbol"),
            "industry_name": row.get("industry_name"),
        }
        for row in candidate_industries.to_dict(orient="records")
    }


def build_industry_checkpoints(
    *,
    stock_quotes: pd.DataFrame,
    industry_members: pd.DataFrame,
    candidate_cutoff_at: datetime,
    execution_cutoff_at: datetime,
) -> dict[str, dict[str, Any]]:
    if stock_quotes.empty or industry_members.empty:
        return {}
    quotes = stock_quotes.merge(industry_members, on="symbol", how="inner")
    stats: dict[str, dict[str, Any]] = {}
    for industry_symbol, group in quotes.groupby("industry_symbol", sort=False):
        candidate_rows = latest_by_symbol_before(group, candidate_cutoff_at)
        execution_rows = latest_by_symbol_before(group, execution_cutoff_at)
        item: dict[str, Any] = {}
        item.update(industry_checkpoint_features("industry_candidate", candidate_rows))
        item.update(industry_checkpoint_features("industry_execution", execution_rows))
        item["industry_execution_up_ratio_delta"] = safe_sub(
            item.get("industry_execution_up_ratio"),
            item.get("industry_candidate_up_ratio"),
        )
        item["industry_execution_avg_ret_delta"] = safe_sub(
            item.get("industry_execution_avg_ret_prev_close"),
            item.get("industry_candidate_avg_ret_prev_close"),
        )
        item["industry_execution_strong_3pct_delta"] = safe_sub(
            item.get("industry_execution_strong_3pct_count"),
            item.get("industry_candidate_strong_3pct_count"),
        )
        stats[str(industry_symbol)] = item
    return stats


def build_official_industry_checkpoints(
    *,
    industry_quotes: pd.DataFrame,
    candidate_cutoff_at: datetime,
    execution_cutoff_at: datetime,
) -> dict[str, dict[str, Any]]:
    if industry_quotes.empty:
        return {}
    stats: dict[str, dict[str, Any]] = {}
    for industry_symbol, group in industry_quotes.groupby("symbol", sort=False):
        candidate_quote = nearest_before(group, candidate_cutoff_at)
        execution_quote = nearest_before(group, execution_cutoff_at)
        item: dict[str, Any] = {}
        item.update(
            official_industry_checkpoint_features("official_industry_candidate", candidate_quote)
        )
        item.update(
            official_industry_checkpoint_features("official_industry_execution", execution_quote)
        )
        item["official_industry_execution_ret_delta"] = safe_sub(
            item.get("official_industry_execution_ret_prev_close"),
            item.get("official_industry_candidate_ret_prev_close"),
        )
        stats[str(industry_symbol)] = item
    return stats


def build_index_checkpoints(
    *,
    index_quotes: pd.DataFrame,
    candidate_cutoff_at: datetime,
    execution_cutoff_at: datetime,
) -> dict[str, Any]:
    if index_quotes.empty:
        return {}
    names = {
        "000001.SH": "sse",
        "399001.SZ": "szse",
        "399006.SZ": "chinext",
        "000300.SH": "hs300",
        "000852.SH": "zz1000",
    }
    output: dict[str, Any] = {}
    checkpoints = (
        ("market_index_candidate", candidate_cutoff_at),
        ("market_index_execution", execution_cutoff_at),
    )
    for prefix, cutoff_at in checkpoints:
        latest = latest_by_symbol_before(index_quotes, cutoff_at)
        if latest.empty:
            continue
        latest = latest.copy()
        latest["ret_prev_close"] = latest.apply(
            lambda row: ratio(row.get("last_price"), row.get("previous_close_price")),
            axis=1,
        )
        latest["ret_open"] = latest.apply(
            lambda row: ratio(row.get("last_price"), row.get("open_price")),
            axis=1,
        )
        output[f"{prefix}_count"] = int(latest["symbol"].nunique())
        output[f"{prefix}_up_ratio"] = float((latest["ret_prev_close"] > 0).mean())
        output[f"{prefix}_avg_ret"] = none_float(latest["ret_prev_close"].mean())
        for symbol, name in names.items():
            selected = latest[latest["symbol"].astype(str).eq(symbol)]
            if selected.empty:
                continue
            item = selected.iloc[0]
            output[f"{prefix}_{name}_ret"] = none_float(item.get("ret_prev_close"))
            output[f"{prefix}_{name}_ret_open"] = none_float(item.get("ret_open"))
    return output


def stock_checkpoint_features(prefix: str, row: pd.Series | None) -> dict[str, Any]:
    if row is None:
        return {
            f"{prefix}_snapshot_at": None,
            f"{prefix}_price": None,
            f"{prefix}_ret_prev_close": None,
            f"{prefix}_ret_open": None,
            f"{prefix}_volume_shares": None,
            f"{prefix}_turnover_amount_yuan": None,
        }
    return {
        f"{prefix}_snapshot_at": row.get("snapshot_at"),
        f"{prefix}_price": none_float(row.get("last_price")),
        f"{prefix}_ret_prev_close": ratio(
            row.get("last_price"),
            row.get("previous_close_price"),
        ),
        f"{prefix}_ret_open": ratio(row.get("last_price"), row.get("open_price")),
        f"{prefix}_volume_shares": none_float(row.get("volume_shares")),
        f"{prefix}_turnover_amount_yuan": none_float(row.get("turnover_amount_yuan")),
    }


def industry_checkpoint_features(prefix: str, rows: pd.DataFrame) -> dict[str, Any]:
    if rows.empty:
        return {
            f"{prefix}_member_count": 0,
            f"{prefix}_up_ratio": None,
            f"{prefix}_avg_ret_prev_close": None,
            f"{prefix}_avg_ret_open": None,
            f"{prefix}_strong_3pct_count": None,
        }
    frame = rows.copy()
    frame["ret_prev_close"] = frame.apply(
        lambda row: ratio(row.get("last_price"), row.get("previous_close_price")),
        axis=1,
    )
    frame["ret_open"] = frame.apply(
        lambda row: ratio(row.get("last_price"), row.get("open_price")),
        axis=1,
    )
    return {
        f"{prefix}_member_count": int(frame["symbol"].nunique()),
        f"{prefix}_up_ratio": float((frame["ret_prev_close"] > 0).mean()),
        f"{prefix}_avg_ret_prev_close": none_float(frame["ret_prev_close"].mean()),
        f"{prefix}_avg_ret_open": none_float(frame["ret_open"].mean()),
        f"{prefix}_strong_3pct_count": int((frame["ret_prev_close"] >= 0.03).sum()),
    }


def official_industry_checkpoint_features(
    prefix: str,
    row: pd.Series | None,
) -> dict[str, Any]:
    if row is None:
        return {
            f"{prefix}_snapshot_at": None,
            f"{prefix}_ret_prev_close": None,
            f"{prefix}_ret_open": None,
        }
    return {
        f"{prefix}_snapshot_at": row.get("snapshot_at"),
        f"{prefix}_ret_prev_close": ratio(
            row.get("last_price"),
            row.get("previous_close_price"),
        ),
        f"{prefix}_ret_open": ratio(row.get("last_price"), row.get("open_price")),
    }


def require_columns(frame: pd.DataFrame, *columns: str) -> None:
    missing_columns = [column for column in columns if column not in frame]
    if missing_columns:
        raise ValueError(f"missing candidate columns: {', '.join(missing_columns)}")
