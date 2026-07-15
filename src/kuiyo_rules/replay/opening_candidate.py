from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime, time, timedelta
from typing import cast
from zoneinfo import ZoneInfo

import pandas as pd

from kuiyo_rules.contracts import (
    CandidateEvaluationOutput,
    OpeningCandidateGenerateOutput,
    build_evaluation_input,
    build_generate_input,
    build_tier_input,
    candidate_handoff_from_output,
)
from kuiyo_rules.definitions import ResearchRuleVersion
from kuiyo_rules.evidence import (
    ContentEvidence,
    DatasetQueryRequirement,
    InputEvidence,
    InputSemanticRole,
    KnownTimeConformance,
    QueryIntent,
    dataframe_fingerprint,
    semantic_fingerprint,
)
from kuiyo_rules.execution import canonical_attempt_key
from kuiyo_rules.replay.contracts import (
    ReplayDayPlan,
    ReplayProgress,
    ReplayStageAttempt,
    ReplayStageInputPlan,
    ReplayStageResult,
    ResolvedReplayStageData,
)


class OpeningCandidateReplayPolicy:
    rule_key = "opening_candidate_watch"
    timezone = "Asia/Shanghai"

    def build_day_plan(
        self,
        *,
        rule_version: ResearchRuleVersion,
        trade_date: date,
    ) -> ReplayDayPlan:
        policy = rule_version.decision_policy
        generate = _mapping(policy, "generate")
        timezone = ZoneInfo(self.timezone)
        current = datetime.combine(
            trade_date,
            time.fromisoformat(str(generate["start_time"])),
            tzinfo=timezone,
        )
        end_at = datetime.combine(
            trade_date,
            time.fromisoformat(str(generate["end_time"])),
            tzinfo=timezone,
        )
        interval = int(generate["interval_seconds"])
        attempts: list[ReplayStageAttempt] = []
        while current <= end_at:
            attempts.append(
                ReplayStageAttempt(
                    "generate",
                    canonical_attempt_key("generate", current),
                    current,
                )
            )
            current += timedelta(seconds=interval)
        evaluation_at = datetime.combine(
            trade_date,
            time.fromisoformat(str(_mapping(policy, "evaluate")["cutoff_time"])),
            tzinfo=timezone,
        )
        attempts.extend(
            (
                ReplayStageAttempt(
                    "evaluate",
                    canonical_attempt_key("evaluate", evaluation_at),
                    evaluation_at,
                ),
                ReplayStageAttempt(
                    "tier",
                    canonical_attempt_key("tier", evaluation_at),
                    evaluation_at,
                ),
            )
        )
        return ReplayDayPlan(trade_date, self.timezone, tuple(attempts))

    def should_execute(
        self,
        *,
        attempt: ReplayStageAttempt,
        progress: ReplayProgress,
    ) -> bool:
        primary = primary_generate_result(progress.completed_stages)
        if attempt.stage_key == "generate":
            return primary is None
        if attempt.stage_key == "evaluate":
            return primary is not None
        if attempt.stage_key == "tier":
            return latest_stage(progress.completed_stages, "evaluate") is not None
        raise ValueError(f"unsupported opening candidate stage: {attempt.stage_key}")

    def build_stage_input_plan(
        self,
        *,
        rule_version: ResearchRuleVersion,
        progress: ReplayProgress,
    ) -> ReplayStageInputPlan:
        attempt = _next_attempt(progress)
        requirements = self._requirements(
            rule_version=rule_version,
            progress=progress,
            attempt=attempt,
        )
        return ReplayStageInputPlan(
            self.rule_key,
            rule_version.rule_version,
            rule_version.definition_hash,
            progress.plan.trade_date,
            attempt,
            requirements,
        )

    def build_rule_input(
        self,
        *,
        rule_version: ResearchRuleVersion,
        resolved: ResolvedReplayStageData,
        progress: ReplayProgress,
    ) -> tuple[object, tuple[InputEvidence, ...]]:
        attempt = resolved.plan.attempt
        frames = {item.input_key: item.frame for item in resolved.datasets}
        evidence = [item.evidence for item in resolved.datasets]
        if attempt.stage_key == "generate":
            return (
                build_generate_rule_input(
                    rule_version=rule_version,
                    trade_date=progress.plan.trade_date,
                    cutoff_at=attempt.cutoff_at,
                    frames=frames,
                ),
                tuple(evidence),
            )
        primary = primary_generate_result(progress.completed_stages)
        if primary is None:
            raise ValueError(f"{attempt.stage_key} requires primary generate output")
        candidates = candidate_handoff_from_output(
            cast(OpeningCandidateGenerateOutput, primary.rule_output)
        )
        if attempt.stage_key == "evaluate":
            evidence.insert(
                0,
                stage_output_evidence(
                    primary,
                    input_key="evaluate.candidates",
                    output_contract="opening_candidate.generate.output/v001",
                    frame=candidates,
                    decision_cutoff_at=attempt.cutoff_at,
                ),
            )
            return (
                build_evaluate_rule_input(
                    rule_version=rule_version,
                    trade_date=progress.plan.trade_date,
                    candidate_cutoff_at=primary.attempt.cutoff_at,
                    evaluation_cutoff_at=attempt.cutoff_at,
                    candidates=candidates,
                    frames=frames,
                ),
                tuple(evidence),
            )
        evaluation = latest_stage(progress.completed_stages, "evaluate")
        if evaluation is None:
            raise ValueError("tier requires evaluation output")
        evaluation_frame = cast(CandidateEvaluationOutput, evaluation.rule_output).evaluations
        return (
            build_tier_input(
                trade_date=progress.plan.trade_date,
                cutoff_at=attempt.cutoff_at,
                candidates=candidates,
                evaluations=evaluation_frame,
            ),
            (
                stage_output_evidence(
                    primary,
                    input_key="tier.candidates",
                    output_contract="opening_candidate.generate.output/v001",
                    frame=candidates,
                    decision_cutoff_at=attempt.cutoff_at,
                ),
                stage_output_evidence(
                    evaluation,
                    input_key="tier.evaluations",
                    output_contract="opening_candidate.evaluate.output/v001",
                    frame=evaluation_frame,
                    decision_cutoff_at=attempt.cutoff_at,
                ),
            ),
        )

    def summarize_day(
        self,
        *,
        progress: ReplayProgress,
        errors: Sequence[str],
    ) -> tuple[str, str]:
        quality = aggregate_quality(progress.completed_stages)
        if errors:
            marker = "evaluator:" if any("evaluator:" in item for item in errors) else "input:"
            return ("evaluator_error" if marker == "evaluator:" else "invalid_input"), quality
        if any(result.status == "missing_data" for result in progress.completed_stages):
            return "invalid_input", quality
        if primary_generate_result(progress.completed_stages) is None:
            return "no_candidate", quality
        return "ok", quality

    def _requirements(
        self,
        *,
        rule_version: ResearchRuleVersion,
        progress: ReplayProgress,
        attempt: ReplayStageAttempt,
    ) -> tuple[QueryIntent, ...]:
        trade_date = progress.plan.trade_date
        if attempt.stage_key == "generate":
            lookback = _input_int(rule_version, "daily_lookback_days")
            classification = _input_text(rule_version, "classification_system")
            level = _input_int(rule_version, "industry_level")
            universe = _input_strings(rule_version, "universe_index_symbols")
            return (
                _dataset_query(
                    "generate.trading_calendar",
                    "market.calendar.trading_calendar.daily",
                    trade_date,
                    trade_date,
                    fields=("calendar_code", "calendar_date", "previous_trading_date"),
                    filters={"calendar_code": "cn_a"},
                    semantic_role="runtime_reference",
                ),
                _dataset_query(
                    "generate.universe",
                    "market.index.constituent.monthly",
                    fields=("index_symbol", "member_symbol", "as_of_date"),
                    filters={"index_symbol": universe},
                    allow_full_scan=True,
                ),
                _dataset_query(
                    "generate.stock_reference",
                    "market.stock.reference.on_change",
                    fields=(
                        "symbol", "name", "exchange", "market", "listing_status",
                        "list_date", "delist_date",
                    ),
                    allow_full_scan=True,
                ),
                _dataset_query(
                    "generate.classification",
                    "market.stock.classification.on_change",
                    fields=(
                        "symbol", "classification_system", "level", "industry_symbol",
                        "effective_from", "effective_to",
                    ),
                    filters={"classification_system": classification, "level": level},
                    allow_full_scan=True,
                ),
                _dataset_query(
                    "generate.industry_reference",
                    "market.industry.reference.on_change",
                    fields=("symbol", "name", "classification_system"),
                    filters={"classification_system": classification},
                    semantic_role="annotation",
                    allow_full_scan=True,
                ),
                _dataset_query(
                    "generate.stock_window",
                    "market.stock.quote.window",
                    trade_date,
                    trade_date,
                    time_end=attempt.cutoff_at.time(),
                    fields=(
                        "trade_date", "snapshot_at", "quote_time", "symbol",
                        "previous_close_price", "open_price", "last_price",
                        "volume_shares", "turnover_amount_yuan",
                    ),
                    missing_policy="allow_empty",
                ),
                _dataset_query(
                    "generate.stock_auction",
                    "market.stock.auction.daily",
                    trade_date,
                    trade_date,
                    fields=(
                        "trade_date", "symbol", "auction_price", "auction_volume_shares",
                        "auction_amount_yuan", "previous_close_price", "observed_at",
                    ),
                    missing_policy="allow_empty",
                ),
                _dataset_query(
                    "generate.stock_daily",
                    "market.stock.quote.daily",
                    trade_date - timedelta(days=lookback),
                    trade_date - timedelta(days=1),
                    fields=("trade_date", "symbol", "close_price", "previous_close_price"),
                ),
            )
        primary = primary_generate_result(progress.completed_stages)
        if primary is None:
            raise ValueError("evaluate plan requires primary generate output")
        candidates = candidate_handoff_from_output(
            cast(OpeningCandidateGenerateOutput, primary.rule_output)
        )
        if attempt.stage_key == "evaluate":
            classification = _input_text(rule_version, "classification_system")
            level = _input_int(rule_version, "industry_level")
            return (
                _stage_query(
                    "evaluate.candidates",
                    primary,
                    "opening_candidate.generate.output/v001",
                    candidates,
                ),
                _dataset_query(
                    "evaluate.classification",
                    "market.stock.classification.on_change",
                    fields=("symbol", "industry_symbol", "effective_from", "effective_to"),
                    filters={"classification_system": classification, "level": level},
                    allow_full_scan=True,
                ),
                _dataset_query(
                    "evaluate.industry_reference",
                    "market.industry.reference.on_change",
                    fields=("symbol", "name", "classification_system"),
                    filters={"classification_system": classification},
                    semantic_role="annotation",
                    allow_full_scan=True,
                ),
                _dataset_query(
                    "evaluate.stock_window",
                    "market.stock.quote.window",
                    trade_date,
                    trade_date,
                    time_end=attempt.cutoff_at.time(),
                    fields=(
                        "trade_date", "snapshot_at", "quote_time", "symbol",
                        "previous_close_price", "open_price", "last_price",
                        "volume_shares", "turnover_amount_yuan",
                    ),
                    missing_policy="allow_empty",
                ),
                _dataset_query(
                    "evaluate.industry_window",
                    "market.industry.quote.window",
                    trade_date,
                    trade_date,
                    time_end=attempt.cutoff_at.time(),
                    fields=(
                        "trade_date", "snapshot_at", "quote_time", "classification_system",
                        "symbol", "previous_close_price", "open_price", "last_price",
                        "pct_change", "volume_shares", "turnover_amount_yuan",
                    ),
                    filters={"classification_system": classification},
                    missing_policy="allow_empty",
                ),
                _dataset_query(
                    "evaluate.index_window",
                    "market.index.quote.window",
                    trade_date,
                    trade_date,
                    time_end=attempt.cutoff_at.time(),
                    fields=(
                        "trade_date", "snapshot_at", "quote_time", "symbol",
                        "previous_close_price", "open_price", "last_price", "volume",
                        "turnover_amount_yuan",
                    ),
                    symbols=_input_strings(rule_version, "focus_index_symbols"),
                    missing_policy="allow_empty",
                ),
            )
        evaluation = latest_stage(progress.completed_stages, "evaluate")
        if evaluation is None:
            raise ValueError("tier plan requires evaluation output")
        evaluations = cast(CandidateEvaluationOutput, evaluation.rule_output).evaluations
        return (
            _stage_query(
                "tier.candidates",
                primary,
                "opening_candidate.generate.output/v001",
                candidates,
            ),
            _stage_query(
                "tier.evaluations",
                evaluation,
                "opening_candidate.evaluate.output/v001",
                evaluations,
            ),
        )


def build_generate_rule_input(
    *,
    rule_version: ResearchRuleVersion,
    trade_date: date,
    cutoff_at: datetime,
    frames: Mapping[str, pd.DataFrame],
) -> object:
    calendar = frames["generate.trading_calendar"]
    if calendar.empty or pd.isna(calendar.iloc[0].get("previous_trading_date")):
        raise ValueError(f"previous trading date not found: {trade_date.isoformat()}")
    previous_trade_date = pd.Timestamp(calendar.iloc[0]["previous_trading_date"]).date()
    universe = universe_as_of(frames["generate.universe"], trade_date=trade_date)
    symbols = set(universe.get("member_symbol", pd.Series(dtype="string")).dropna().astype(str))
    references = stock_references_as_of(
        frames["generate.stock_reference"],
        trade_date=trade_date,
    )
    references = references[references["symbol"].astype(str).isin(symbols)]
    classifications = classifications_as_of(
        frames["generate.classification"],
        trade_date=trade_date,
    )
    classifications = classifications[classifications["symbol"].astype(str).isin(symbols)]
    stock_quotes = frames["generate.stock_window"]
    stock_quotes = stock_quotes[stock_quotes["symbol"].astype(str).isin(symbols)]
    auctions = frames["generate.stock_auction"]
    auctions = auctions[auctions["symbol"].astype(str).isin(symbols)]
    return build_generate_input(
        trade_date=trade_date,
        previous_trade_date=previous_trade_date,
        cutoff_at=cutoff_at,
        stock_quotes=prepare_stock_quotes(
            stock_quotes,
            cutoff_at=cutoff_at,
            references=references,
            classifications=classifications,
            industry_references=frames["generate.industry_reference"],
        ),
        auctions=prepare_auctions(auctions, cutoff_at=cutoff_at),
        daily_quotes=prepare_daily_quotes(frames["generate.stock_daily"]),
    )


def build_evaluate_rule_input(
    *,
    rule_version: ResearchRuleVersion,
    trade_date: date,
    candidate_cutoff_at: datetime,
    evaluation_cutoff_at: datetime,
    candidates: pd.DataFrame,
    frames: Mapping[str, pd.DataFrame],
) -> object:
    classifications = classifications_as_of(
        frames["evaluate.classification"],
        trade_date=trade_date,
    )
    candidate_symbols = set(candidates["asset_key"].dropna().astype(str))
    candidate_industries = classifications[
        classifications["symbol"].astype(str).isin(candidate_symbols)
    ][["symbol", "industry_symbol"]].drop_duplicates()
    names = frames["evaluate.industry_reference"][["symbol", "name"]].rename(
        columns={"symbol": "industry_symbol", "name": "industry_name"}
    )
    candidate_industries = candidate_industries.merge(names, on="industry_symbol", how="left")
    industry_symbols = set(candidate_industries["industry_symbol"].dropna().astype(str))
    industry_members = classifications[
        classifications["industry_symbol"].astype(str).isin(industry_symbols)
    ][["symbol", "industry_symbol"]]
    symbols = candidate_symbols.union(industry_members["symbol"].dropna().astype(str))
    stock_quotes = frames["evaluate.stock_window"]
    stock_quotes = stock_quotes[stock_quotes["symbol"].astype(str).isin(symbols)]
    industry_quotes = frames["evaluate.industry_window"]
    industry_quotes = industry_quotes[
        industry_quotes["symbol"].astype(str).isin(industry_symbols)
    ]
    index_quotes = frames["evaluate.index_window"]
    focus = set(_input_strings(rule_version, "focus_index_symbols"))
    index_quotes = index_quotes[index_quotes["symbol"].astype(str).isin(focus)]
    return build_evaluation_input(
        trade_date=trade_date,
        candidate_cutoff_at=candidate_cutoff_at,
        evaluation_cutoff_at=evaluation_cutoff_at,
        candidates=candidates,
        stock_quotes=stock_quotes,
        candidate_industries=candidate_industries,
        industry_members=industry_members,
        industry_quotes=industry_quotes,
        index_quotes=index_quotes,
    )


def latest_stage(
    completed: Sequence[ReplayStageResult],
    stage_key: str,
) -> ReplayStageResult | None:
    return next(
        (item for item in reversed(completed) if item.attempt.stage_key == stage_key),
        None,
    )


def primary_generate_result(
    completed: Sequence[ReplayStageResult],
) -> ReplayStageResult | None:
    for result in completed:
        if result.attempt.stage_key != "generate" or result.status != "ok":
            continue
        output = cast(OpeningCandidateGenerateOutput, result.rule_output)
        if int(output.summary.get("primary_candidate_count", 0)) > 0:
            return result
    return None


def aggregate_quality(completed: Sequence[ReplayStageResult]) -> str:
    qualities = [result.data_quality for result in completed]
    for quality in ("missing", "degraded", "partial", "proxy", "stale"):
        if quality in qualities:
            return quality
    return "normal"


def stage_output_evidence(
    upstream: ReplayStageResult,
    *,
    input_key: str,
    output_contract: str,
    frame: pd.DataFrame,
    decision_cutoff_at: datetime,
) -> InputEvidence:
    fingerprint = dataframe_fingerprint(frame)
    decision_inputs = tuple(
        item for item in upstream.input_evidence if item.query.semantic_role == "decision"
    )
    statuses = [item.conformance.status for item in decision_inputs]
    capabilities = [item.conformance.temporal_capability for item in decision_inputs]
    reasons = tuple(
        dict.fromkeys(
            reason for item in decision_inputs for reason in item.conformance.reasons
        )
    )
    captured_at = max(
        (item.conformance.captured_at for item in upstream.input_evidence),
        default=upstream.attempt.cutoff_at,
    )
    return InputEvidence(
        query=QueryIntent(
            input_key,
            "stage_output",
            {},
            upstream_stage_key=upstream.attempt.stage_key,
            upstream_attempt_key=upstream.attempt.attempt_key,
            upstream_output_contract=output_contract,
            upstream_content_fingerprint=fingerprint,
        ),
        resolved_sources=(),
        content=ContentEvidence(
            row_count=len(frame),
            entity_count=_frame_entity_count(frame),
            observation_count=len(frame),
            content_fingerprint=fingerprint,
            max_known_at=upstream.attempt.cutoff_at.isoformat(),
            quality=upstream.data_quality,
            quality_reasons=(),
        ),
        conformance=KnownTimeConformance(
            decision_cutoff_at=decision_cutoff_at,
            capture_mode="historical_reconstruction",
            captured_at=captured_at,
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
                if not statuses or "degraded" in statuses
                else "valid"
            ),
            reasons=reasons,
        ),
    )


def universe_as_of(frame: pd.DataFrame, *, trade_date: date) -> pd.DataFrame:
    if frame.empty:
        return frame
    output = frame.copy()
    output["as_of_date"] = pd.to_datetime(output["as_of_date"], errors="coerce").dt.date
    output = output[output["as_of_date"].notna() & (output["as_of_date"] <= trade_date)]
    if output.empty:
        return output
    latest = output.groupby("index_symbol", dropna=False)["as_of_date"].transform("max")
    return output[output["as_of_date"].eq(latest)].reset_index(drop=True)


def classifications_as_of(frame: pd.DataFrame, *, trade_date: date) -> pd.DataFrame:
    if frame.empty:
        return frame
    output = frame.copy()
    output["effective_from"] = pd.to_datetime(output["effective_from"], errors="coerce")
    output["effective_to"] = pd.to_datetime(output["effective_to"], errors="coerce")
    as_of = pd.Timestamp(trade_date)
    active = output["effective_from"].notna() & (output["effective_from"] <= as_of)
    active &= output["effective_to"].isna() | (output["effective_to"] >= as_of)
    return output[active].sort_values(["symbol", "effective_from"]).drop_duplicates(
        subset=["symbol"], keep="last"
    ).reset_index(drop=True)


def stock_references_as_of(frame: pd.DataFrame, *, trade_date: date) -> pd.DataFrame:
    if frame.empty:
        return frame
    output = frame.copy()
    output["list_date"] = pd.to_datetime(output["list_date"], errors="coerce")
    output["delist_date"] = pd.to_datetime(output["delist_date"], errors="coerce")
    as_of = pd.Timestamp(trade_date)
    active = output["list_date"].isna() | (output["list_date"] <= as_of)
    active &= output["delist_date"].isna() | (output["delist_date"] >= as_of)
    output = output[active].copy()
    output["listing_status"] = "listed"
    return output.drop(columns=["list_date", "delist_date"]).reset_index(drop=True)


def prepare_stock_quotes(
    frame: pd.DataFrame,
    *,
    cutoff_at: datetime,
    references: pd.DataFrame,
    classifications: pd.DataFrame,
    industry_references: pd.DataFrame,
) -> pd.DataFrame:
    if frame.empty:
        return frame
    output = frame.copy()
    output["trade_date"] = pd.to_datetime(output["trade_date"]).dt.date
    output["snapshot_at"] = pd.to_datetime(output["snapshot_at"])
    output["quote_time"] = pd.to_datetime(output["quote_time"])
    output = output[output["snapshot_at"] < pd.Timestamp(cutoff_at)]
    output = output.sort_values(["symbol", "snapshot_at"]).groupby("symbol", sort=False).tail(1)
    output = output.merge(references, on="symbol", how="left")
    output = output.merge(classifications[["symbol", "industry_symbol"]], on="symbol", how="left")
    names = industry_references[["symbol", "name"]].rename(
        columns={"symbol": "industry_symbol", "name": "industry_name"}
    )
    output = output.merge(names, on="industry_symbol", how="left")
    for column in (
        "previous_close_price", "open_price", "last_price", "volume_shares",
        "turnover_amount_yuan",
    ):
        output[column] = pd.to_numeric(output[column], errors="coerce")
    return output.reset_index(drop=True)


def prepare_auctions(frame: pd.DataFrame, *, cutoff_at: datetime) -> pd.DataFrame:
    if frame.empty:
        return frame
    output = frame.copy()
    output["trade_date"] = pd.to_datetime(output["trade_date"]).dt.date
    output["observed_at"] = pd.to_datetime(output["observed_at"])
    output = output[output["observed_at"].isna() | (output["observed_at"] < cutoff_at)]
    for column in (
        "auction_price", "auction_volume_shares", "auction_amount_yuan",
        "previous_close_price",
    ):
        output[column] = pd.to_numeric(output[column], errors="coerce")
    return output.reset_index(drop=True)


def prepare_daily_quotes(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    output = frame.copy()
    output["trade_date"] = pd.to_datetime(output["trade_date"]).dt.date
    output["close_price"] = pd.to_numeric(output["close_price"], errors="coerce")
    output["previous_close_price"] = pd.to_numeric(
        output["previous_close_price"], errors="coerce"
    )
    output["day_ret"] = output["close_price"] / output["previous_close_price"] - 1.0
    return output


def _dataset_query(
    input_key: str,
    dataset_key: str,
    date_start: date | None = None,
    date_end: date | None = None,
    *,
    time_end: time | None = None,
    fields: tuple[str, ...] = (),
    filters: Mapping[str, object] | None = None,
    semantic_role: str = "decision",
    missing_policy: str = "warn",
    allow_full_scan: bool = False,
    symbols: tuple[str, ...] = (),
) -> DatasetQueryRequirement:
    canonical_symbols = tuple(dict.fromkeys(symbols))
    query = QueryIntent(
        input_key=input_key,
        input_type="dataset",
        requested_range={
            "date_start": date_start,
            "date_end": date_end,
            "time_end": time_end,
        },
        semantic_role=cast(InputSemanticRole, semantic_role),
        dataset_key=dataset_key,
        fields=fields,
        filters=dict(filters or {}),
        symbol_count=len(canonical_symbols),
        symbol_set_fingerprint=(
            semantic_fingerprint(tuple(sorted(canonical_symbols)))
            if canonical_symbols
            else None
        ),
        missing_policy=missing_policy,
    )
    return DatasetQueryRequirement(query, canonical_symbols, allow_full_scan)


def _stage_query(
    input_key: str,
    upstream: ReplayStageResult,
    output_contract: str,
    frame: pd.DataFrame,
) -> QueryIntent:
    return QueryIntent(
        input_key,
        "stage_output",
        {},
        upstream_stage_key=upstream.attempt.stage_key,
        upstream_attempt_key=upstream.attempt.attempt_key,
        upstream_output_contract=output_contract,
        upstream_content_fingerprint=dataframe_fingerprint(frame),
    )


def _mapping(container: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = container.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f"invalid rule decision policy: {key}")
    return value


def _input_text(version: ResearchRuleVersion, key: str) -> str:
    value = version.input_contract.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"invalid rule input contract value: {key}")
    return value


def _input_int(version: ResearchRuleVersion, key: str) -> int:
    value = version.input_contract.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"invalid rule input contract value: {key}")
    return int(value)


def _input_strings(version: ResearchRuleVersion, key: str) -> tuple[str, ...]:
    value = version.input_contract.get(key)
    if not isinstance(value, tuple) or not value:
        raise ValueError(f"invalid rule input contract value: {key}")
    return tuple(str(item) for item in value)


def _next_attempt(progress: ReplayProgress) -> ReplayStageAttempt:
    if progress.next_attempt is None:
        raise ValueError("replay is already complete")
    return progress.next_attempt


def _frame_entity_count(frame: pd.DataFrame) -> int:
    for column in ("candidate_key", "asset_key", "symbol"):
        if column in frame:
            return int(frame[column].nunique(dropna=True))
    return 0


OPENING_CANDIDATE_REPLAY_POLICY = OpeningCandidateReplayPolicy()
