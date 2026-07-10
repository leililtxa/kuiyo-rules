from __future__ import annotations

from collections.abc import Iterable

import pandas as pd


QUALITY_PRIORITY = ("missing", "degraded", "partial", "proxy", "stale")


def aggregate_data_quality(values: Iterable[object], *, default: str = "normal") -> str:
    qualities = {clean_quality(value) for value in values}
    qualities.discard("")
    if not qualities:
        return default
    for quality in QUALITY_PRIORITY:
        if quality in qualities:
            return quality
    return default


def clean_quality(value: object) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value)

