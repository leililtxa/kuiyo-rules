from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime, time, timedelta
from typing import cast

import pandas as pd

from kuiyo_rules.contracts import (
    CandidateEvaluationInput,
    OpeningCandidateGenerateInput,
)
from kuiyo_rules.definitions import ResearchRuleVersion
from kuiyo_rules.definitions.input_contract import (
    rule_input_int,
    rule_input_strings,
    rule_input_text,
)
from kuiyo_rules.evidence.contracts import (
    ConformanceStatus,
    ContentEvidence,
    EvidenceCaptureContext,
    InputEvidence,
    InputSemanticRole,
    KnownTimeConformance,
    QueryIntent,
    ResolutionEvidence,
    ResolvedSourceEvidence,
)
from kuiyo_rules.evidence.fingerprints import (
    dataframe_fingerprint,
    semantic_fingerprint,
)


def generate_execution_evidence(
    rule_input: OpeningCandidateGenerateInput,
    *,
    rule_version: ResearchRuleVersion,
    resolutions: Mapping[str, ResolutionEvidence],
    capture_context: EvidenceCaptureContext | None = None,
) -> tuple[InputEvidence, ...]:
    capture = capture_context or historical_capture_context(
        tuple(resolutions.values()),
        default=rule_input.cutoff_at,
    )
    previous_trade_date_frame = pd.DataFrame(
        [
            {
                "trade_date": rule_input.trade_date,
                "previous_trade_date": rule_input.previous_trade_date,
            }
        ]
    )
    previous_close = datetime.combine(
        rule_input.previous_trade_date,
        time(15, 0),
        tzinfo=rule_input.cutoff_at.tzinfo,
    )
    stock_known = frame_datetime(rule_input.stock_quotes, ("snapshot_at", "quote_time"))
    auction_known = frame_datetime(rule_input.auctions, ("observed_at",))
    daily_known = frame_trade_date_at_close(
        rule_input.daily_quotes,
        timezone=rule_input.cutoff_at.tzinfo,
    )
    universe_symbols = rule_input_strings(rule_version, "universe_index_symbols")
    return (
        dataset_execution_evidence(
            input_key="generate.previous_trade_date",
            dataset_key="market.calendar.trading_calendar.daily",
            frame=previous_trade_date_frame,
            cutoff_at=rule_input.cutoff_at,
            resolutions=(resolutions["generate.trading_calendar"],),
            requested_range={"trade_date": rule_input.trade_date},
            filters={"calendar_code": "cn_a"},
            min_known_at=previous_close,
            max_known_at=previous_close,
            semantic_role="runtime_reference",
            capture_context=capture,
        ),
        dataset_execution_evidence(
            input_key="generate.stock_quotes",
            dataset_key="market.stock.quote.window",
            frame=rule_input.stock_quotes,
            cutoff_at=rule_input.cutoff_at,
            resolutions=tuple(
                resolutions[key]
                for key in (
                    "generate.universe",
                    "generate.stock_reference",
                    "generate.classification",
                    "generate.industry_reference",
                    "generate.stock_window",
                )
            ),
            requested_range={
                "trade_date": rule_input.trade_date,
                "time_end_exclusive": rule_input.cutoff_at,
                "known_at": rule_input.cutoff_at,
            },
            filters={
                "universe_index_symbols": universe_symbols,
                "classification_system": rule_input_text(
                    rule_version, "classification_system"
                ),
                "industry_level": rule_input_int(rule_version, "industry_level"),
                "selection": "latest_snapshot_per_symbol",
            },
            min_known_at=stock_known[0],
            max_known_at=stock_known[1],
            capture_context=capture,
        ),
        dataset_execution_evidence(
            input_key="generate.auctions",
            dataset_key="market.stock.auction.daily",
            frame=rule_input.auctions,
            cutoff_at=rule_input.cutoff_at,
            resolutions=(resolutions["generate.stock_auction"],),
            requested_range={"trade_date": rule_input.trade_date},
            filters={"observed_at_before": rule_input.cutoff_at},
            min_known_at=auction_known[0],
            max_known_at=auction_known[1],
            empty_status="degraded",
            empty_reason="auction_input_empty_proxy_possible",
            capture_context=capture,
        ),
        dataset_execution_evidence(
            input_key="generate.daily_quotes",
            dataset_key="market.stock.quote.daily",
            frame=rule_input.daily_quotes,
            cutoff_at=rule_input.cutoff_at,
            resolutions=(resolutions["generate.stock_daily"],),
            requested_range={
                "date_start": rule_input.trade_date
                - timedelta(
                    days=rule_input_int(rule_version, "daily_lookback_days")
                ),
                "date_end_exclusive": rule_input.trade_date,
            },
            filters={},
            min_known_at=daily_known[0],
            max_known_at=daily_known[1],
            capture_context=capture,
        ),
    )


def evaluate_execution_evidence(
    rule_input: CandidateEvaluationInput,
    *,
    rule_version: ResearchRuleVersion,
    resolutions: Mapping[str, ResolutionEvidence],
    candidate_evidence: InputEvidence,
    capture_context: EvidenceCaptureContext | None = None,
) -> tuple[InputEvidence, ...]:
    capture = capture_context or historical_capture_context(
        tuple(resolutions.values()),
        default=rule_input.evaluation_cutoff_at,
    )
    stock_known = frame_datetime(rule_input.stock_quotes, ("snapshot_at", "quote_time"))
    industry_known = frame_datetime(
        rule_input.industry_quotes, ("snapshot_at", "quote_time")
    )
    index_known = frame_datetime(rule_input.index_quotes, ("snapshot_at", "quote_time"))
    classification_known = datetime.combine(
        rule_input.trade_date,
        time(0, 0),
        tzinfo=rule_input.evaluation_cutoff_at.tzinfo,
    )
    classification_resolutions = (
        resolutions["evaluate.classification"],
        resolutions["evaluate.industry_reference"],
    )
    return (
        candidate_evidence,
        dataset_execution_evidence(
            input_key="evaluate.candidate_industries",
            dataset_key="market.stock.classification.on_change",
            frame=rule_input.candidate_industries,
            cutoff_at=rule_input.evaluation_cutoff_at,
            resolutions=classification_resolutions,
            requested_range={
                "trade_date": rule_input.trade_date,
                "known_at": rule_input.evaluation_cutoff_at,
            },
            filters={"selection": "candidate_symbols_as_of"},
            min_known_at=classification_known,
            max_known_at=classification_known,
            capture_context=capture,
        ),
        dataset_execution_evidence(
            input_key="evaluate.industry_members",
            dataset_key="market.stock.classification.on_change",
            frame=rule_input.industry_members,
            cutoff_at=rule_input.evaluation_cutoff_at,
            resolutions=(resolutions["evaluate.classification"],),
            requested_range={
                "trade_date": rule_input.trade_date,
                "known_at": rule_input.evaluation_cutoff_at,
            },
            filters={"selection": "candidate_industries_as_of"},
            min_known_at=classification_known,
            max_known_at=classification_known,
            capture_context=capture,
        ),
        dataset_execution_evidence(
            input_key="evaluate.stock_quotes",
            dataset_key="market.stock.quote.window",
            frame=rule_input.stock_quotes,
            cutoff_at=rule_input.evaluation_cutoff_at,
            resolutions=(resolutions["evaluate.stock_window"],),
            requested_range={
                "trade_date": rule_input.trade_date,
                "time_end_exclusive": rule_input.evaluation_cutoff_at,
            },
            filters={"selection": "candidate_and_industry_members"},
            min_known_at=stock_known[0],
            max_known_at=stock_known[1],
            capture_context=capture,
        ),
        dataset_execution_evidence(
            input_key="evaluate.industry_quotes",
            dataset_key="market.industry.quote.window",
            frame=rule_input.industry_quotes,
            cutoff_at=rule_input.evaluation_cutoff_at,
            resolutions=(resolutions["evaluate.industry_window"],),
            requested_range={
                "trade_date": rule_input.trade_date,
                "time_end_exclusive": rule_input.evaluation_cutoff_at,
            },
            filters={"selection": "candidate_industries"},
            min_known_at=industry_known[0],
            max_known_at=industry_known[1],
            capture_context=capture,
        ),
        dataset_execution_evidence(
            input_key="evaluate.index_quotes",
            dataset_key="market.index.quote.window",
            frame=rule_input.index_quotes,
            cutoff_at=rule_input.evaluation_cutoff_at,
            resolutions=(resolutions["evaluate.index_window"],),
            requested_range={
                "trade_date": rule_input.trade_date,
                "time_end_exclusive": rule_input.evaluation_cutoff_at,
            },
            filters={
                "symbols": rule_input_strings(rule_version, "focus_index_symbols")
            },
            min_known_at=index_known[0],
            max_known_at=index_known[1],
            capture_context=capture,
        ),
    )


def dataset_execution_evidence(
    *,
    input_key: str,
    dataset_key: str,
    frame: pd.DataFrame,
    cutoff_at: datetime,
    resolutions: Sequence[ResolutionEvidence],
    requested_range: Mapping[str, object],
    filters: Mapping[str, object],
    min_known_at: datetime | None,
    max_known_at: datetime | None,
    capture_context: EvidenceCaptureContext,
    semantic_role: str = "decision",
    empty_status: str = "invalid",
    empty_reason: str = "input_empty",
) -> InputEvidence:
    row_count = len(frame)
    symbols = frame_symbols(frame)
    resolution_reasons = tuple(
        dict.fromkeys(
            reason
            for resolution in resolutions
            for reason in resolution.content.quality_reasons
        )
    )
    quality = aggregate_resolution_quality(resolutions)
    reasons: tuple[str, ...] = ()
    status = "valid"
    if not row_count:
        quality = "missing" if empty_status == "invalid" else "degraded"
        status = empty_status
        reasons = (empty_reason,)
    elif max_known_at is None:
        quality = "degraded"
        status = "degraded"
        reasons = ("known_at_unavailable",)
    elif max_known_at > cutoff_at:
        quality = "missing"
        status = "invalid"
        reasons = ("known_after_decision_cutoff",)
    return InputEvidence(
        query=QueryIntent(
            input_key=input_key,
            input_type="dataset",
            requested_range=dict(requested_range),
            semantic_role=cast(InputSemanticRole, semantic_role),
            dataset_key=dataset_key,
            fields=tuple(sorted(str(column) for column in frame.columns)),
            filters=dict(filters),
            symbol_count=len(symbols),
            symbol_set_fingerprint=(
                semantic_fingerprint(symbols) if symbols else None
            ),
            missing_policy="allow_empty",
        ),
        resolved_sources=merge_resolved_sources(resolutions),
        content=ContentEvidence(
            row_count=row_count,
            entity_count=_frame_entity_count(frame),
            observation_count=row_count,
            content_fingerprint=dataframe_fingerprint(frame),
            min_known_at=iso_or_none(min_known_at),
            max_known_at=iso_or_none(max_known_at),
            quality=quality,
            quality_reasons=tuple(dict.fromkeys((*resolution_reasons, *reasons))),
            effective_date_start=iso_or_none(min_frame_date(frame)),
            effective_date_end=iso_or_none(max_frame_date(frame)),
            effective_time_start=iso_or_none(min_known_at),
            effective_time_end=iso_or_none(max_known_at),
        ),
        conformance=KnownTimeConformance(
            decision_cutoff_at=cutoff_at,
            capture_mode=capture_context.capture_mode,
            captured_at=capture_context.captured_at,
            temporal_capability="point_in_time",
            status=cast(ConformanceStatus, status),
            reasons=reasons,
        ),
    )


def historical_capture_context(
    resolutions: Sequence[ResolutionEvidence],
    *,
    default: datetime,
) -> EvidenceCaptureContext:
    return EvidenceCaptureContext(
        "historical_reconstruction",
        max((item.captured_at for item in resolutions), default=default),
    )


def merge_resolved_sources(
    resolutions: Sequence[ResolutionEvidence],
) -> tuple[ResolvedSourceEvidence, ...]:
    output: list[ResolvedSourceEvidence] = []
    seen: set[tuple[str, str]] = set()
    for resolution in resolutions:
        for source in resolution.resolved_sources:
            identity = (source.storage_type, source.location)
            if identity not in seen:
                seen.add(identity)
                output.append(source)
    return tuple(output)


def aggregate_resolution_quality(resolutions: Sequence[ResolutionEvidence]) -> str:
    qualities = {item.content.quality for item in resolutions}
    for quality in ("missing", "partial", "degraded", "stale"):
        if quality in qualities:
            return quality
    return "normal"


def frame_symbols(frame: pd.DataFrame) -> tuple[str, ...]:
    for column in ("symbol", "asset_key", "candidate_key"):
        if column in frame:
            return tuple(sorted(frame[column].dropna().astype(str).unique()))
    return ()


def _frame_entity_count(frame: pd.DataFrame) -> int:
    for column in ("candidate_key", "asset_key", "symbol"):
        if column in frame:
            return int(frame[column].nunique(dropna=True))
    return len(frame)


def frame_datetime(
    frame: pd.DataFrame,
    fields: Sequence[str],
) -> tuple[datetime | None, datetime | None]:
    for field in fields:
        if field not in frame:
            continue
        values = pd.to_datetime(frame[field], errors="coerce").dropna()
        if not values.empty:
            return values.min().to_pydatetime(), values.max().to_pydatetime()
    return None, None


def frame_trade_date_at_close(
    frame: pd.DataFrame,
    *,
    timezone,
) -> tuple[datetime | None, datetime | None]:
    if "trade_date" not in frame:
        return None, None
    values = pd.to_datetime(frame["trade_date"], errors="coerce").dropna()
    if values.empty:
        return None, None
    return (
        datetime.combine(values.min().date(), time(15, 0), tzinfo=timezone),
        datetime.combine(values.max().date(), time(15, 0), tzinfo=timezone),
    )


def min_frame_date(frame: pd.DataFrame) -> date | None:
    return frame_date(frame, "min")


def max_frame_date(frame: pd.DataFrame) -> date | None:
    return frame_date(frame, "max")


def frame_date(frame: pd.DataFrame, operation: str) -> date | None:
    if "trade_date" not in frame:
        return None
    values = pd.to_datetime(frame["trade_date"], errors="coerce").dropna()
    if values.empty:
        return None
    value = values.min() if operation == "min" else values.max()
    return value.date()


def iso_or_none(value: object) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return str(value.isoformat())
    return str(value)


def stage_output_execution_evidence(
    *,
    input_key: str,
    upstream_stage_key: str,
    upstream_attempt_key: str,
    output_contract: str,
    frame: pd.DataFrame,
    upstream_cutoff_at: datetime,
    decision_cutoff_at: datetime,
    data_quality: str,
    upstream_input_evidence: Sequence[InputEvidence],
    capture_context: EvidenceCaptureContext,
) -> InputEvidence:
    fingerprint = dataframe_fingerprint(frame)
    decision_inputs = tuple(
        item for item in upstream_input_evidence if item.query.semantic_role == "decision"
    )
    statuses = [item.conformance.status for item in decision_inputs]
    capabilities = [item.conformance.temporal_capability for item in decision_inputs]
    reasons = tuple(
        dict.fromkeys(
            reason for item in decision_inputs for reason in item.conformance.reasons
        )
    )
    if not statuses:
        statuses = [
            "valid"
            if data_quality == "normal"
            else "invalid"
            if data_quality == "missing"
            else "degraded"
        ]
    if not capabilities:
        capabilities = ["point_in_time"]
    return InputEvidence(
        query=QueryIntent(
            input_key,
            "stage_output",
            {},
            upstream_stage_key=upstream_stage_key,
            upstream_attempt_key=upstream_attempt_key,
            upstream_output_contract=output_contract,
            upstream_content_fingerprint=fingerprint,
        ),
        resolved_sources=(),
        content=ContentEvidence(
            row_count=len(frame),
            entity_count=_frame_entity_count(frame),
            observation_count=len(frame),
            content_fingerprint=fingerprint,
            min_known_at=upstream_cutoff_at.isoformat(),
            max_known_at=upstream_cutoff_at.isoformat(),
            quality=data_quality,
            quality_reasons=(),
        ),
        conformance=KnownTimeConformance(
            decision_cutoff_at=decision_cutoff_at,
            capture_mode=capture_context.capture_mode,
            captured_at=capture_context.captured_at,
            temporal_capability=(
                "current_snapshot"
                if "current_snapshot" in capabilities
                else "point_in_time"
                if capabilities and all(item == "point_in_time" for item in capabilities)
                else "unknown"
            ),
            status=(
                "invalid"
                if "invalid" in statuses
                else "degraded"
                if "degraded" in statuses
                else "valid"
            ),
            reasons=reasons,
        ),
    )
