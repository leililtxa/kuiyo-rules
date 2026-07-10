from __future__ import annotations

from datetime import date, datetime
from typing import Any

import pandas as pd


def enrich_stock_rows(
    *,
    trade_date: date,
    previous_trade_date: date,
    cutoff_at: datetime,
    stock_quotes: pd.DataFrame,
    auctions: pd.DataFrame,
    daily_quotes: pd.DataFrame,
    allow_auction_proxy: bool,
) -> pd.DataFrame:
    out = stock_quotes.copy()
    out["name"] = out["name"].fillna(out["symbol"])
    out["industry_name"] = out["industry_name"].fillna(out["industry_symbol"])
    out["stock_ret_prev_close_0935"] = out["last_price"] / out["previous_close_price"] - 1.0
    out["stock_ret_open_0935"] = out["last_price"] / out["open_price"] - 1.0
    out["amount"] = out["turnover_amount_yuan"]
    out["volume"] = out["volume_shares"]
    snapshot_at = out["snapshot_at"].max()
    out["selected_snapshot_at"] = snapshot_at
    out["snapshot_gap_seconds"] = (pd.Timestamp(cutoff_at) - snapshot_at).total_seconds()
    out = out.merge(
        known_stock_features(daily_quotes=daily_quotes, previous_trade_date=previous_trade_date),
        on="symbol",
        how="left",
    )
    if not auctions.empty:
        auction_columns = [
            "symbol",
            "auction_price",
            "auction_amount_yuan",
            "previous_close_price",
            "observed_at",
        ]
        out = out.merge(
            auctions[auction_columns].rename(columns={"previous_close_price": "auction_previous_close_price"}),
            on="symbol",
            how="left",
        )
    else:
        out["auction_price"] = pd.NA
        out["auction_amount_yuan"] = pd.NA
        out["auction_previous_close_price"] = pd.NA
        out["observed_at"] = pd.NaT

    effective_auction = out["auction_price"].fillna(out["open_price"]) if allow_auction_proxy else out["auction_price"]
    effective_previous = out["auction_previous_close_price"].fillna(out["previous_close_price"])
    out["auction_ret_prev_close"] = effective_auction / effective_previous - 1.0
    out["auction_amount"] = out["auction_amount_yuan"]
    out["auction_data_quality"] = "normal"
    proxy_mask = out["auction_price"].isna() & allow_auction_proxy & out["open_price"].notna()
    missing_mask = out["auction_price"].isna() & (~allow_auction_proxy | out["open_price"].isna())
    out.loc[proxy_mask, "auction_data_quality"] = "proxy"
    out.loc[missing_mask, "auction_data_quality"] = "missing"
    out["auction_data_quality_reason"] = ""
    out.loc[out["auction_data_quality"].eq("proxy"), "auction_data_quality_reason"] = "open_price_proxy"
    out.loc[out["auction_data_quality"].eq("missing"), "auction_data_quality_reason"] = "open_auction_missing"
    return out[out["industry_symbol"].notna()].copy()


def known_stock_features(*, daily_quotes: pd.DataFrame, previous_trade_date: date) -> pd.DataFrame:
    if daily_quotes.empty:
        return pd.DataFrame(
            columns=["symbol", "known_prev_trade_date", "known_prev_day_ret", "known_ret_3d", "known_ret_5d"]
        )
    rows: list[dict[str, Any]] = []
    usable = daily_quotes[daily_quotes["trade_date"] <= previous_trade_date].sort_values(["symbol", "trade_date"])
    for symbol, group in usable.groupby("symbol", sort=False):
        closes = list(pd.to_numeric(group["close_price"], errors="coerce"))
        dates = list(group["trade_date"])
        day_returns = list(pd.to_numeric(group["day_ret"], errors="coerce"))
        if not closes or dates[-1] != previous_trade_date:
            continue
        latest_close = closes[-1]
        rows.append(
            {
                "symbol": symbol,
                "known_prev_trade_date": dates[-1],
                "known_prev_day_ret": day_returns[-1],
                "known_ret_3d": latest_close / closes[-4] - 1.0 if len(closes) >= 4 and closes[-4] else pd.NA,
                "known_ret_5d": latest_close / closes[-6] - 1.0 if len(closes) >= 6 and closes[-6] else pd.NA,
            }
        )
    return pd.DataFrame(rows)

