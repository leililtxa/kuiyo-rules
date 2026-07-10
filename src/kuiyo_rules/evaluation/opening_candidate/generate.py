from __future__ import annotations

import pandas as pd

from kuiyo_rules.contracts import OpeningCandidateGenerateInput, OpeningCandidateGenerateOutput
from kuiyo_rules.definitions import ResearchRuleVersion
from kuiyo_rules.evaluation.opening_candidate.features import enrich_stock_rows
from kuiyo_rules.evaluation.opening_candidate.industry import build_industry_stats
from kuiyo_rules.evaluation.opening_candidate.market_policy import (
    build_market_policy,
    missing_market_policy,
    missing_previous_daily_market_policy,
    result_data_quality,
)
from kuiyo_rules.evaluation.opening_candidate.parameters import generate_parameters
from kuiyo_rules.evaluation.opening_candidate.selection import (
    build_ranked_pool,
    diversify_candidates,
    select_industries,
    select_shadow_industries,
)


def generate_opening_candidates(
    *,
    rule_version: ResearchRuleVersion,
    rule_input: OpeningCandidateGenerateInput,
) -> OpeningCandidateGenerateOutput:
    parameters = generate_parameters(rule_version)
    stock_quotes = rule_input.stock_quotes
    auctions = rule_input.auctions
    daily_quotes = rule_input.daily_quotes

    if stock_quotes.empty:
        return OpeningCandidateGenerateOutput(
            status="missing_data",
            data_quality="missing",
            market_policy=missing_market_policy("no_realtime_before_cutoff"),
            selected_industries=pd.DataFrame(),
            candidates=pd.DataFrame(),
            summary={
                "reason": "no_realtime_before_cutoff",
                "realtime_row_count": 0,
                "rule": rule_identity(rule_version),
            },
        )

    previous_daily = (
        daily_quotes[daily_quotes["trade_date"] == rule_input.previous_trade_date]
        if not daily_quotes.empty
        else pd.DataFrame()
    )
    if previous_daily.empty:
        snapshot_at = stock_quotes["snapshot_at"].max() if "snapshot_at" in stock_quotes else pd.NaT
        if pd.isna(snapshot_at):
            market_policy = missing_market_policy("missing_previous_daily_quotes")
        else:
            snapshot_gap_seconds = (
                pd.Timestamp(rule_input.cutoff_at) - pd.Timestamp(snapshot_at)
            ).total_seconds()
            market_policy = missing_previous_daily_market_policy(
                trade_date=rule_input.trade_date,
                previous_trade_date=rule_input.previous_trade_date,
                cutoff_at=rule_input.cutoff_at,
                snapshot_at=snapshot_at,
                snapshot_gap_seconds=float(snapshot_gap_seconds),
                parameters=parameters,
            )
        return OpeningCandidateGenerateOutput(
            status="missing_data",
            data_quality="missing",
            market_policy=market_policy,
            selected_industries=pd.DataFrame(),
            candidates=pd.DataFrame(),
            summary={
                "reason": "missing_previous_daily_quotes",
                "realtime_row_count": int(len(stock_quotes)),
                "auction_row_count": int(len(auctions)),
                "daily_row_count": int(len(daily_quotes)),
                "previous_trading_date": rule_input.previous_trade_date.isoformat(),
                "previous_daily_row_count": 0,
                "industry_count": 0,
                "selected_industry_count": 0,
                "candidate_count": 0,
                "market_policy": market_policy,
                "rule": rule_identity(rule_version),
            },
        )

    enriched = enrich_stock_rows(
        trade_date=rule_input.trade_date,
        previous_trade_date=rule_input.previous_trade_date,
        cutoff_at=rule_input.cutoff_at,
        stock_quotes=stock_quotes,
        auctions=auctions,
        daily_quotes=daily_quotes,
        allow_auction_proxy=parameters.allow_auction_proxy,
    )
    if enriched.empty:
        snapshot_at = stock_quotes["snapshot_at"].max() if "snapshot_at" in stock_quotes else pd.NaT
        if pd.isna(snapshot_at):
            market_policy = missing_market_policy("no_enriched_stock_rows")
            data_quality = "missing"
        else:
            snapshot_gap_seconds = (
                pd.Timestamp(rule_input.cutoff_at) - pd.Timestamp(snapshot_at)
            ).total_seconds()
            market_policy = build_market_policy(
                trade_date=rule_input.trade_date,
                previous_trade_date=rule_input.previous_trade_date,
                cutoff_at=rule_input.cutoff_at,
                daily_quotes=daily_quotes,
                industry_stats=pd.DataFrame(),
                snapshot_at=snapshot_at,
                snapshot_gap_seconds=float(snapshot_gap_seconds),
                parameters=parameters,
            )
            data_quality = "missing" if daily_quotes.empty else "degraded"
        return OpeningCandidateGenerateOutput(
            status="no_candidate",
            data_quality=data_quality,
            market_policy=market_policy,
            selected_industries=pd.DataFrame(),
            candidates=pd.DataFrame(),
            summary={
                "reason": "no_enriched_stock_rows",
                "realtime_row_count": int(len(stock_quotes)),
                "auction_row_count": int(len(auctions)),
                "daily_row_count": int(len(daily_quotes)),
                "industry_count": 0,
                "selected_industry_count": 0,
                "candidate_count": 0,
                "market_policy": market_policy,
                "rule": rule_identity(rule_version),
            },
        )

    industry_stats = build_industry_stats(enriched, parameters=parameters)
    market_policy = build_market_policy(
        trade_date=rule_input.trade_date,
        previous_trade_date=rule_input.previous_trade_date,
        cutoff_at=rule_input.cutoff_at,
        daily_quotes=daily_quotes,
        industry_stats=industry_stats,
        snapshot_at=enriched["selected_snapshot_at"].iloc[0],
        snapshot_gap_seconds=float(enriched["snapshot_gap_seconds"].iloc[0]),
        parameters=parameters,
    )
    selected_industries = select_industries(
        industry_stats=industry_stats,
        market_policy=market_policy,
        parameters=parameters,
    )
    ranked_pool = build_ranked_pool(
        enriched=enriched,
        selected_industries=selected_industries,
        parameters=parameters,
    )
    selected = diversify_candidates(ranked_pool, parameters=parameters)
    primary_candidate_count = int(len(selected))
    shadow_candidate_count = 0
    shadow_pool = pd.DataFrame()
    if selected.empty and parameters.enable_shadow_candidates:
        shadow_industries = select_shadow_industries(
            industry_stats=industry_stats,
            market_policy=market_policy,
            parameters=parameters,
        )
        shadow_pool = build_ranked_pool(
            enriched=enriched,
            selected_industries=shadow_industries,
            parameters=parameters,
        )
        shadow_selected = diversify_candidates(shadow_pool, parameters=parameters)
        if not shadow_selected.empty:
            selected_industries = shadow_industries
            selected = shadow_selected
            shadow_candidate_count = int(len(selected))

    data_quality = result_data_quality(
        selected=selected,
        market_policy=market_policy,
        daily_quotes=daily_quotes,
    )
    status = "ok" if not selected.empty else "no_candidate"
    return OpeningCandidateGenerateOutput(
        status=status,
        data_quality=data_quality,
        market_policy=market_policy,
        selected_industries=selected_industries,
        candidates=selected,
        summary={
            "realtime_row_count": int(len(stock_quotes)),
            "auction_row_count": int(len(auctions)),
            "daily_row_count": int(len(daily_quotes)),
            "industry_count": int(len(industry_stats)),
            "selected_industry_count": int(len(selected_industries)),
            "candidate_count": int(len(selected)),
            "market_policy": market_policy,
            "parameters": {
                "classification_system": parameters.classification_system,
                "industry_level": parameters.industry_level,
                "min_industry_members": parameters.minimum_industry_members,
                "max_industries_restricted": parameters.restricted_industry_limit,
                "max_industries_normal": parameters.normal_industry_limit,
                "max_stocks_per_industry": parameters.maximum_stocks_per_industry,
                "enable_shadow_candidates": parameters.enable_shadow_candidates,
                "max_shadow_industries": parameters.shadow_industry_limit,
                "snapshot_max_gap_seconds": parameters.snapshot_max_gap_seconds,
                "daily_lookback_days": int(rule_version.input_contract["daily_lookback_days"]),
                "allow_auction_proxy": parameters.allow_auction_proxy,
                "universe_index_symbols": list(rule_version.input_contract["universe_index_symbols"]),
            },
            "primary_candidate_count": primary_candidate_count,
            "shadow_candidate_count": shadow_candidate_count,
            "ranked_pool_count": int(len(ranked_pool)),
            "shadow_ranked_pool_count": int(len(shadow_pool)),
            "rule": rule_identity(rule_version),
        },
        ranked_pool=ranked_pool,
        shadow_ranked_pool=shadow_pool,
    )


def rule_identity(rule_version: ResearchRuleVersion) -> dict[str, str]:
    return {
        "rule_key": rule_version.rule_key,
        "rule_version": rule_version.rule_version,
        "definition_hash": rule_version.definition_hash,
    }
