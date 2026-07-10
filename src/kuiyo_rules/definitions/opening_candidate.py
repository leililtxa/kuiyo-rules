from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from kuiyo_rules.clauses.models import RuleClauseReference
from kuiyo_rules.definitions.models import ResearchRuleDefinition, ResearchRuleVersion


OPENING_CANDIDATE_DEFINITION = ResearchRuleDefinition(
    rule_key="opening_candidate_watch",
    name="Opening Candidate Watch",
    decision_purpose="Generate and evaluate opening-session stock candidates.",
    output_type="candidate_set",
    input_contract_key="opening_candidate_watch.input",
    output_contract_key="opening_candidate_watch.output",
    description="Opening candidate generation, execution confirmation, and watch tiering.",
)


OPENING_CANDIDATE_BASELINE_V001 = ResearchRuleVersion(
    rule_key=OPENING_CANDIDATE_DEFINITION.rule_key,
    rule_version="v001",
    lifecycle_status="proposed",
    provenance_status="pending_review",
    input_contract_version="v001",
    output_contract_version="v001",
    decision_policy={
        "generate": {
            "mode": "polling",
            "start_time": "09:36",
            "end_time": "09:46",
            "interval_seconds": 60,
            "success_policy": "primary_candidate_exists",
            "accept_shadow_candidate": False,
        },
        "evaluate": {"cutoff_time": "09:46"},
        "tier": {"after_stage": "evaluate"},
    },
    known_time_contract={
        "stock_window": "snapshot_at < cutoff_at",
        "auction": "observed_at is null or observed_at < cutoff_at",
        "daily": "trade_date < rule trade_date",
        "membership_mode": "current_snapshot",
        "classification_mode": "current_snapshot",
    },
    input_contract={
        "dataset_keys": [
            "market.stock.quote.window",
            "market.stock.auction.daily",
            "market.stock.quote.daily",
            "market.index.constituent.monthly",
            "market.stock.classification.on_change",
            "market.industry.quote.window",
            "market.index.quote.window",
        ],
        "universe_index_symbols": ["000300.SH", "000852.SH"],
        "classification_system": "sw2021",
        "industry_level": 1,
        "daily_lookback_days": 30,
    },
    clause_composition=(
        RuleClauseReference(
            clause_key="opening.market-policy",
            clause_version="v001",
            clause_type="decision",
            source_refs=("RW-20-BL-market-policy",),
            parameters={"weak_breadth": 0.40, "strong_breadth": 0.55},
        ),
        RuleClauseReference(
            clause_key="opening.industry-strength",
            clause_version="v001",
            clause_type="decision",
            source_refs=("RW-20-BL-industry-strength",),
            parameters={
                "minimum_members": 8,
                "restricted_limit": 3,
                "normal_limit": 5,
                "enable_shadow_candidates": True,
                "shadow_limit": 3,
                "very_strong_breadth": 0.65,
                "very_strong_average_return": 0.01,
                "very_strong_minimum_3pct_count": 1,
                "strong_breadth": 0.55,
                "strong_average_return": 0.005,
                "moderate_breadth": 0.50,
                "moderate_average_return": 0.0,
            },
        ),
        RuleClauseReference(
            clause_key="opening.stock-eligibility",
            clause_version="v001",
            clause_type="decision",
            source_refs=("RW-20-BL-stock-eligibility",),
            parameters={
                "limit_like_return": 0.095,
                "minimum_return_previous_close": 0.0,
                "minimum_return_open": 0.0,
                "known_5d_max": 0.15,
                "known_3d_min": -0.08,
                "previous_day_min": -0.07,
                "auction_return_min": -0.03,
            },
        ),
        RuleClauseReference(
            clause_key="opening.candidate-scoring",
            clause_version="v001",
            clause_type="decision",
            source_refs=("RW-20-BL-candidate-scoring",),
            parameters={
                "industry_return_weight": 0.35,
                "stock_return_weight": 0.25,
                "stock_open_return_weight": 0.20,
                "stock_amount_weight": 0.20,
                "known_5d_penalty_first_threshold": 0.15,
                "known_5d_penalty_second_threshold": 0.20,
                "known_5d_penalty_weight": 0.10,
                "max_stocks_per_industry": 2,
            },
        ),
        RuleClauseReference(
            clause_key="opening.execution-confirmation",
            clause_version="v001",
            clause_type="decision",
            source_refs=("RW-20-BL-execution-confirmation",),
            parameters={
                "stock_fade": -0.005,
                "stock_continuation": 0.005,
                "industry_breadth_fade": -0.15,
                "industry_return_fade": -0.005,
                "critical_hard_tags": [
                    "hard_below_open_execution",
                    "hard_industry_breadth_fade_execution",
                    "hard_industry_return_fade_execution",
                ],
                "minimum_hard_tags_to_reject": 2,
                "strong_confirm_soft_tags": 4,
                "confirm_soft_tags": 3,
                "weak_confirm_soft_tags": 2,
                "strong_confirm_premium": 0.010,
                "confirm_premium": 0.005,
                "weak_confirm_premium": 0.002,
                "elevated_chase": 0.05,
                "high_chase": 0.08,
            },
        ),
        RuleClauseReference(
            clause_key="opening.watch-tier",
            clause_version="v001",
            clause_type="decision",
            source_refs=("RW-20-BL-watch-tier",),
            parameters={
                "faded_before_execution": -0.01,
                "stable_after_candidate": -0.005,
                "continued_after_candidate": 0.005,
                "already_hot": 0.07,
                "elevated_chase": 0.05,
                "high_chase": 0.08,
            },
        ),
        RuleClauseReference(
            clause_key="opening.data-quality-guard",
            clause_version="v001",
            clause_type="invariant",
            source_refs=("RW-20-data-quality-contract",),
            parameters={"snapshot_max_gap_seconds": 120, "allow_auction_proxy": True},
        ),
    ),
    output_contract={
        "stages": ["generate", "evaluate", "tier"],
        "candidate_roles": ["watch", "shadow"],
        "data_quality": ["normal", "proxy", "stale", "partial", "missing", "degraded"],
        "generate_status": ["ok", "no_candidate", "missing_data"],
        "evaluation_decisions": ["invalid", "reject", "observe", "weak_confirm", "confirm", "strong_confirm"],
        "watch_levels": ["focus_watch", "secondary_watch", "observe_only", "reject"],
    },
    source_hypothesis_keys=(),
    frozen_at=datetime(2026, 7, 10, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
    metadata={
        "legacy_rule_key": "opening_candidate_watch_0936",
        "legacy_rule_version": "v0.2",
        "baseline_inventory": "RW-20-baseline-rule-inventory",
    },
)
