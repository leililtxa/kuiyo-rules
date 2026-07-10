from __future__ import annotations

from datetime import datetime

import pandas as pd


def latest_by_symbol_before(
    frame: pd.DataFrame,
    cutoff_at: datetime,
    *,
    symbol_column: str = "symbol",
    time_column: str = "snapshot_at",
) -> pd.DataFrame:
    if frame.empty:
        return frame
    usable = frame[frame[time_column] < pd.Timestamp(cutoff_at)]
    if usable.empty:
        return usable
    return (
        usable.sort_values([symbol_column, time_column])
        .groupby(symbol_column, sort=False)
        .tail(1)
    )


def nearest_before(
    frame: pd.DataFrame,
    cutoff_at: datetime,
    *,
    time_column: str = "snapshot_at",
) -> pd.Series | None:
    if frame.empty:
        return None
    usable = frame[frame[time_column] < pd.Timestamp(cutoff_at)]
    if usable.empty:
        return None
    return usable.sort_values(time_column).iloc[-1]
