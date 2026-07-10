from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from kuiyo_rules.clauses import RuleClauseReference
from kuiyo_rules.definitions import ResearchRuleVersion


@dataclass(frozen=True)
class OpeningCandidateGenerateParameters:
    classification_system: str
    industry_level: int
    minimum_industry_members: int
    restricted_industry_limit: int
    normal_industry_limit: int
    enable_shadow_candidates: bool
    shadow_industry_limit: int
    maximum_stocks_per_industry: int
    snapshot_max_gap_seconds: int
    allow_auction_proxy: bool
    weak_market_breadth: float
    strong_market_breadth: float
    very_strong_industry_breadth: float
    very_strong_industry_average_return: float
    very_strong_industry_minimum_3pct_count: int
    strong_industry_breadth: float
    strong_industry_average_return: float
    moderate_industry_breadth: float
    moderate_industry_average_return: float
    limit_like_return: float
    minimum_return_previous_close: float
    minimum_return_open: float
    known_5d_max: float
    known_3d_min: float
    previous_day_min: float
    auction_return_min: float
    industry_return_weight: float
    stock_return_weight: float
    stock_open_return_weight: float
    stock_amount_weight: float
    known_5d_penalty_first_threshold: float
    known_5d_penalty_second_threshold: float
    known_5d_penalty_weight: float


def generate_parameters(version: ResearchRuleVersion) -> OpeningCandidateGenerateParameters:
    if version.rule_key != "opening_candidate_watch":
        raise ValueError(f"unsupported generate rule: {version.rule_key}")
    market = clause_parameters(version, "opening.market-policy")
    industry = clause_parameters(version, "opening.industry-strength")
    eligibility = clause_parameters(version, "opening.stock-eligibility")
    scoring = clause_parameters(version, "opening.candidate-scoring")
    quality = clause_parameters(version, "opening.data-quality-guard")
    return OpeningCandidateGenerateParameters(
        classification_system=text_value(version.input_contract, "classification_system"),
        industry_level=int_value(version.input_contract, "industry_level"),
        minimum_industry_members=int_value(industry, "minimum_members"),
        restricted_industry_limit=int_value(industry, "restricted_limit"),
        normal_industry_limit=int_value(industry, "normal_limit"),
        enable_shadow_candidates=bool_value(industry, "enable_shadow_candidates"),
        shadow_industry_limit=int_value(industry, "shadow_limit"),
        maximum_stocks_per_industry=int_value(scoring, "max_stocks_per_industry"),
        snapshot_max_gap_seconds=int_value(quality, "snapshot_max_gap_seconds"),
        allow_auction_proxy=bool_value(quality, "allow_auction_proxy"),
        weak_market_breadth=float_value(market, "weak_breadth"),
        strong_market_breadth=float_value(market, "strong_breadth"),
        very_strong_industry_breadth=float_value(industry, "very_strong_breadth"),
        very_strong_industry_average_return=float_value(industry, "very_strong_average_return"),
        very_strong_industry_minimum_3pct_count=int_value(industry, "very_strong_minimum_3pct_count"),
        strong_industry_breadth=float_value(industry, "strong_breadth"),
        strong_industry_average_return=float_value(industry, "strong_average_return"),
        moderate_industry_breadth=float_value(industry, "moderate_breadth"),
        moderate_industry_average_return=float_value(industry, "moderate_average_return"),
        limit_like_return=float_value(eligibility, "limit_like_return"),
        minimum_return_previous_close=float_value(eligibility, "minimum_return_previous_close"),
        minimum_return_open=float_value(eligibility, "minimum_return_open"),
        known_5d_max=float_value(eligibility, "known_5d_max"),
        known_3d_min=float_value(eligibility, "known_3d_min"),
        previous_day_min=float_value(eligibility, "previous_day_min"),
        auction_return_min=float_value(eligibility, "auction_return_min"),
        industry_return_weight=float_value(scoring, "industry_return_weight"),
        stock_return_weight=float_value(scoring, "stock_return_weight"),
        stock_open_return_weight=float_value(scoring, "stock_open_return_weight"),
        stock_amount_weight=float_value(scoring, "stock_amount_weight"),
        known_5d_penalty_first_threshold=float_value(scoring, "known_5d_penalty_first_threshold"),
        known_5d_penalty_second_threshold=float_value(scoring, "known_5d_penalty_second_threshold"),
        known_5d_penalty_weight=float_value(scoring, "known_5d_penalty_weight"),
    )


def clause_parameters(version: ResearchRuleVersion, clause_key: str) -> Mapping[str, object]:
    matches: list[RuleClauseReference] = [
        clause for clause in version.clause_composition if clause.clause_key == clause_key
    ]
    if len(matches) != 1:
        raise ValueError(f"expected one clause {clause_key!r}, found {len(matches)}")
    return matches[0].parameters


def text_value(values: Mapping[str, object], key: str) -> str:
    value = required_value(values, key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def int_value(values: Mapping[str, object], key: str) -> int:
    value = required_value(values, key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{key} must be numeric")
    return int(value)


def float_value(values: Mapping[str, object], key: str) -> float:
    value = required_value(values, key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{key} must be numeric")
    return float(value)


def bool_value(values: Mapping[str, object], key: str) -> bool:
    value = required_value(values, key)
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be boolean")
    return value


def required_value(values: Mapping[str, object], key: str) -> object:
    if key not in values:
        raise ValueError(f"missing rule parameter: {key}")
    return values[key]
