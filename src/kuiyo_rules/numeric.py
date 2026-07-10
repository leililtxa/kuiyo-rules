from __future__ import annotations

import pandas as pd


def none_if_missing(value: object) -> object | None:
    if value is None:
        return None
    try:
        if bool(pd.isna(value)):
            return None
    except (TypeError, ValueError):
        pass
    return value


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


def missing(value: object) -> bool:
    return none_float(value) is None


def safe_sub(left: object, right: object) -> float | None:
    left_value = none_float(left)
    right_value = none_float(right)
    if left_value is None or right_value is None:
        return None
    return left_value - right_value


def number_lt(value: object, target: float) -> bool:
    current = none_float(value)
    return current is not None and current < target


def number_le(value: object, target: float) -> bool:
    current = none_float(value)
    return current is not None and current <= target


def number_gt(value: object, target: float) -> bool:
    current = none_float(value)
    return current is not None and current > target


def number_ge(value: object, target: float) -> bool:
    current = none_float(value)
    return current is not None and current >= target
