from __future__ import annotations

import pandas as pd


def none_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return float(value)


def ratio(numerator: object, denominator: object) -> float | None:
    n = none_float(numerator)
    d = none_float(denominator)
    if n is None or d is None or d == 0:
        return None
    return n / d - 1.0

