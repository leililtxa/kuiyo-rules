from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

import pandas as pd


JsonObject = dict[str, Any]


def empty_frame() -> pd.DataFrame:
    return pd.DataFrame()


@dataclass(frozen=True)
class OpeningCandidateGenerateInput:
    trade_date: date
    previous_trade_date: date
    cutoff_at: datetime
    stock_quotes: pd.DataFrame
    auctions: pd.DataFrame
    daily_quotes: pd.DataFrame


@dataclass(frozen=True)
class OpeningCandidateGenerateOutput:
    status: str
    data_quality: str
    market_policy: JsonObject
    selected_industries: pd.DataFrame
    candidates: pd.DataFrame
    summary: JsonObject
    ranked_pool: pd.DataFrame = field(default_factory=empty_frame)
    shadow_ranked_pool: pd.DataFrame = field(default_factory=empty_frame)


@dataclass(frozen=True)
class CandidateEvaluationInput:
    trade_date: date
    candidate_cutoff_at: datetime
    evaluation_cutoff_at: datetime
    candidates: pd.DataFrame
    stock_quotes: pd.DataFrame
    candidate_industries: pd.DataFrame
    industry_members: pd.DataFrame
    industry_quotes: pd.DataFrame
    index_quotes: pd.DataFrame


@dataclass(frozen=True)
class CandidateEvaluationOutput:
    status: str
    data_quality: str
    evaluations: pd.DataFrame
    summary: JsonObject


@dataclass(frozen=True)
class CandidateTierInput:
    trade_date: date
    cutoff_at: datetime
    candidates: pd.DataFrame
    evaluations: pd.DataFrame


@dataclass(frozen=True)
class CandidateTierOutput:
    status: str
    data_quality: str
    tiers: pd.DataFrame
    summary: JsonObject

