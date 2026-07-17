from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict
from datetime import date, timedelta
from typing import cast

import pandas as pd

from kuiyo_rules.audit.contracts import (
    AuditAsOf,
    AuditResult,
    AuditSummary,
    OutcomePlan,
    OutcomeRequirement,
    ResolvedOutcomeBundle,
    validate_audit_inputs,
)
from kuiyo_rules.audit.facts import (
    AuditIdentity,
    ClauseObservationFact,
    DistributionFact,
    EvidenceCohort,
    HealthWindowFact,
    MaturityStatus,
    ReplayDayFact,
    ReplayInputFact,
    ReplayStageFact,
    SubjectOutcomeFact,
)
from kuiyo_rules.audit.parity import (
    ProductionReplayParity,
    ProductionStageEvidence,
    compare_production_replay,
)
from kuiyo_rules.audit.specifications import AuditSpecification, OutcomeDefinition
from kuiyo_rules.contracts import (
    CandidateEvaluationOutput,
    CandidateTierOutput,
    OpeningCandidateGenerateOutput,
    candidate_handoff_from_output,
)
from kuiyo_rules.evidence import (
    QueryIntent,
    input_evidence_semantic_fingerprint,
    semantic_fingerprint,
)
from kuiyo_rules.replay import ReplayDayResult, ReplayResult
from kuiyo_rules.replay.opening_candidate import latest_stage, primary_generate_result


OPENING_CANDIDATE_AUDIT_V001 = AuditSpecification(
    audit_spec_key="AUDIT-001",
    audit_spec_version="v001",
    target_rule_key="opening_candidate_watch",
    supported_rule_versions=("v001",),
    outcome_definitions=(
        OutcomeDefinition("t_close", "T", "candidate_reference_price", "number", False),
        OutcomeDefinition("t_peak", "T", "candidate_reference_price", "number", False),
        OutcomeDefinition("t_drawdown", "T", "candidate_reference_price", "number", False),
        OutcomeDefinition("t_close_retention", "T", "post_cutoff_peak", "number", False),
        OutcomeDefinition("t1_open", "T+1", "candidate_reference_price", "number", True),
        OutcomeDefinition("t1_close", "T+1", "candidate_reference_price", "number", True),
        OutcomeDefinition("t3_close", "T+3", "candidate_reference_price", "number", True),
        OutcomeDefinition("t5_close", "T+5", "candidate_reference_price", "number", True),
    ),
    group_dimensions=(
        "evidence_cohort",
        "candidate_role",
        "evaluation_decision",
        "watch_level",
    ),
)


OUTCOME_VALUE_COLUMNS = {
    "t_close": "t_close_return",
    "t_peak": "t_peak_return",
    "t_drawdown": "t_drawdown_return",
    "t_close_retention": "t_close_retention",
    "t1_open": "t1_open_return",
    "t1_close": "t1_close_return",
    "t3_close": "t3_close_return",
    "t5_close": "t5_close_return",
}


def build_opening_candidate_outcome_plan(
    *,
    replay: ReplayResult,
    specification: AuditSpecification,
    as_of: AuditAsOf,
) -> OutcomePlan:
    identity = audit_identity(replay, specification)
    candidates = candidate_decisions(replay.days)
    if candidates.empty:
        return OutcomePlan(identity, as_of, ())
    symbols = tuple(sorted(candidates["candidate_key"].astype(str).unique()))
    trade_dates = tuple(sorted(candidates["trade_date"].unique()))
    requirements = (
        _outcome_requirement(
            "outcome.calendar",
            as_of.as_of_date,
            "market.calendar.trading_calendar.daily",
            min(trade_dates),
            as_of.as_of_date + timedelta(days=14),
            fields=("calendar_date", "is_trading_day"),
            filters={"calendar_code": "cn_a"},
        ),
        _outcome_requirement(
            "outcome.stock_daily",
            as_of.as_of_date,
            "market.stock.quote.daily",
            min(trade_dates),
            as_of.as_of_date,
            fields=(
                "trade_date", "symbol", "open_price", "close_price",
                "up_limit_price", "down_limit_price",
            ),
            filters={},
            symbols=symbols,
        ),
        _outcome_requirement(
            "outcome.stock_window",
            as_of.as_of_date,
            "market.stock.quote.window",
            min(trade_dates),
            max(trade_dates),
            fields=("trade_date", "snapshot_at", "symbol", "last_price"),
            filters={},
            symbols=symbols,
        ),
        _outcome_requirement(
            "outcome.stock_minute",
            as_of.as_of_date,
            "market.stock.quote.minute",
            min(trade_dates),
            max(trade_dates),
            fields=("trade_date", "quote_time", "symbol", "high_price", "low_price"),
            filters={},
            symbols=symbols,
        ),
    )
    return OutcomePlan(identity, as_of, requirements)


def compute_opening_candidate_audit(
    *,
    replay: ReplayResult,
    specification: AuditSpecification,
    outcome_plan: OutcomePlan,
    outcome_bundle: ResolvedOutcomeBundle,
    production_evidence: Sequence[ProductionStageEvidence] = (),
) -> AuditResult:
    validate_audit_inputs(
        replay=replay,
        outcome_plan=outcome_plan,
        outcome_bundle=outcome_bundle,
    )
    identity = outcome_plan.identity
    frames = {item.requirement_key: item.frame for item in outcome_bundle.inputs}
    candidates = candidate_decisions(replay.days)
    if candidates.empty:
        enriched = candidates
    else:
        horizons = trading_horizon_map(
            frames["outcome.calendar"],
            trade_dates=tuple(sorted(candidates["trade_date"].unique())),
            horizons=(1, 3, 5),
        )
        enriched = enrich_candidate_outcomes(
            candidates,
            daily_quotes=frames["outcome.stock_daily"],
            window_quotes=frames["outcome.stock_window"],
            minute_quotes=frames["outcome.stock_minute"],
            horizons=horizons,
        )
    parity = compare_production_replay(production_evidence, replay.days)
    replay_days = tuple(replay_day_fact(identity, item, parity) for item in replay.days)
    replay_stages = tuple(
        replay_stage_fact(day, stage, parity)
        for day in replay.days
        for stage in day.stages
    )
    replay_inputs = tuple(
        replay_input_fact(day, stage, evidence, parity)
        for day in replay.days
        for stage in day.stages
        for evidence in stage.input_evidence
    )
    clause_observations = tuple(
        clause_fact(day, stage, trace)
        for day in replay.days
        for stage in day.stages
        for trace in stage.clause_traces
    )
    subject_outcomes = build_subject_outcomes(
        enriched,
        specification=specification,
        as_of=outcome_plan.as_of,
        source_identity=outcome_source_identity(outcome_bundle),
    )
    distributions = build_distributions(
        subject_outcomes,
        specification=specification,
        cohort_start=outcome_plan.as_of.cohort_start_date,
        as_of_date=outcome_plan.as_of.as_of_date,
    )
    health_windows = build_health_windows(
        replay_days,
        subject_outcomes,
        specification=specification,
    )
    pending = sum(item.maturity_status == "pending" for item in subject_outcomes)
    unavailable = sum(item.maturity_status == "unavailable" for item in subject_outcomes)
    invalid = sum(item.evidence_cohort == "invalid" for item in replay_days)
    computed_days = len({item.trade_date for item in replay_days if item.evidence_cohort != "invalid"})
    coverage = (
        "invalid"
        if replay_days and invalid == len(replay_days)
        else "incomplete"
        if unavailable
        else "maturing"
        if pending
        else "complete"
    )
    summary = AuditSummary(
        identity,
        outcome_plan.as_of.as_of_date,
        outcome_plan.as_of.cohort_start_date,
        len(replay.days),
        computed_days,
        pending,
        invalid,
        unavailable,
        coverage,
        {
            "candidate_count": len(candidates),
            "subject_outcome_count": len(subject_outcomes),
        },
    )
    return AuditResult(
        summary,
        replay_days,
        replay_stages,
        replay_inputs,
        subject_outcomes,
        clause_observations,
        distributions,
        health_windows,
    )


def audit_identity(
    replay: ReplayResult,
    specification: AuditSpecification,
) -> AuditIdentity:
    if replay.rule_key != specification.target_rule_key:
        raise ValueError("audit specification target does not match replay rule")
    if replay.rule_version not in specification.supported_rule_versions:
        raise ValueError("audit specification does not support replay rule version")
    return AuditIdentity(
        replay.rule_key,
        replay.rule_version,
        replay.rule_definition_hash,
        specification.audit_spec_key,
        specification.audit_spec_version,
        specification.definition_hash,
    )


def candidate_decisions(replays: Sequence[ReplayDayResult]) -> pd.DataFrame:
    parts: list[pd.DataFrame] = []
    for replay in replays:
        primary = primary_generate_result(replay.stages)
        if primary is None:
            continue
        handoff = candidate_handoff_from_output(
            cast(OpeningCandidateGenerateOutput, primary.rule_output)
        )
        if handoff.empty:
            continue
        generated = handoff.copy()
        generated["candidate_key"] = generated["asset_key"].astype(str)
        generated["candidate_cutoff_at"] = primary.attempt.cutoff_at
        generated["candidate_reference_price"] = generated["metrics"].map(
            lambda value: value.get("last_price") if isinstance(value, Mapping) else None
        )
        generated["candidate_data_quality"] = generated["data_quality"]
        generated["replay_status"] = replay.status
        generated["replay_data_quality"] = replay.data_quality
        generated["evidence_cohort"] = evidence_cohort(replay.status, replay.data_quality)
        generated = merge_stage_labels(replay, generated)
        parts.append(generated)
    return pd.concat(parts, ignore_index=True, sort=False) if parts else pd.DataFrame()


def merge_stage_labels(replay: ReplayDayResult, candidates: pd.DataFrame) -> pd.DataFrame:
    output = candidates
    evaluation = latest_stage(replay.stages, "evaluate")
    if evaluation is not None:
        frame = cast(CandidateEvaluationOutput, evaluation.rule_output).evaluations.copy()
        if not frame.empty:
            frame["candidate_key"] = frame["candidate_key"].astype(str)
            output = output.merge(
                frame[["candidate_key", "decision", "data_quality"]].rename(
                    columns={
                        "decision": "evaluation_decision",
                        "data_quality": "evaluation_data_quality",
                    }
                ),
                on="candidate_key",
                how="left",
            )
    tier = latest_stage(replay.stages, "tier")
    if tier is not None:
        frame = cast(CandidateTierOutput, tier.rule_output).tiers.copy()
        if not frame.empty:
            frame["candidate_key"] = frame["asset_key"].astype(str)
            output = output.merge(
                frame[["candidate_key", "watch_level", "data_quality"]].rename(
                    columns={"data_quality": "tier_data_quality"}
                ),
                on="candidate_key",
                how="left",
            )
    return output


def trading_horizon_map(
    calendar: pd.DataFrame,
    *,
    trade_dates: Sequence[date],
    horizons: Sequence[int],
) -> dict[date, dict[int, date | None]]:
    if calendar.empty:
        return {item: {horizon: None for horizon in horizons} for item in trade_dates}
    frame = calendar.copy()
    frame["calendar_date"] = pd.to_datetime(frame["calendar_date"]).dt.date
    trading_days = sorted(
        frame.loc[frame["is_trading_day"].astype(bool), "calendar_date"].dropna().unique()
    )
    positions = {value: index for index, value in enumerate(trading_days)}
    return {
        item: {
            horizon: (
                trading_days[positions[item] + horizon]
                if item in positions and positions[item] + horizon < len(trading_days)
                else None
            )
            for horizon in horizons
        }
        for item in trade_dates
    }


def enrich_candidate_outcomes(
    candidates: pd.DataFrame,
    *,
    daily_quotes: pd.DataFrame,
    window_quotes: pd.DataFrame,
    minute_quotes: pd.DataFrame,
    horizons: Mapping[date, Mapping[int, date | None]],
) -> pd.DataFrame:
    if candidates.empty:
        return candidates
    daily = _normalize_daily(daily_quotes)
    window = _normalize_intraday(window_quotes, "snapshot_at")
    minute = _normalize_intraday(minute_quotes, "quote_time")
    rows = [
        _enrich_candidate_row(
            row,
            daily=daily,
            window=window,
            minute=minute,
            horizons=horizons,
        )
        for row in candidates.to_dict(orient="records")
    ]
    return pd.DataFrame(rows)


def build_subject_outcomes(
    frame: pd.DataFrame,
    *,
    specification: AuditSpecification,
    as_of: AuditAsOf,
    source_identity: Mapping[str, object],
) -> tuple[SubjectOutcomeFact, ...]:
    facts: list[SubjectOutcomeFact] = []
    for row in frame.to_dict(orient="records"):
        trade_date = pd.Timestamp(row["trade_date"]).date()
        reference = _number(row.get("candidate_reference_price"))
        dimensions = {
            key: _json_scalar(row.get(key))
            for key in specification.group_dimensions
        }
        for definition in specification.outcome_definitions:
            value = _number(row.get(OUTCOME_VALUE_COLUMNS[definition.outcome_key]))
            target = _target_date(row, trade_date, definition.horizon)
            if reference is None and definition.reference_key == "candidate_reference_price":
                maturity, quality, reasons = "invalid", "missing", ("reference_unavailable",)
            elif target is None or target > as_of.as_of_date:
                maturity, quality, reasons = "pending", "normal", ()
            elif value is None:
                maturity, quality, reasons = "unavailable", "partial", ("outcome_unavailable",)
            else:
                maturity, quality, reasons = (
                    "mature",
                    str(row.get("outcome_data_quality") or "normal"),
                    tuple(row.get("outcome_quality_reasons") or ()),
                )
            facts.append(
                SubjectOutcomeFact(
                    trade_date=trade_date,
                    subject_type="stock_candidate",
                    subject_key=str(row["candidate_key"]),
                    subject_role=str(row.get("candidate_role") or "watch"),
                    outcome_key=definition.outcome_key,
                    horizon=definition.horizon,
                    target_trade_date=target,
                    maturity_status=cast(MaturityStatus, maturity),
                    value_type=definition.value_type,
                    executable=definition.executable,
                    data_quality=quality,
                    computation_mode="initial",
                    value_number=value if maturity == "mature" else None,
                    reference_value=reference,
                    quality_reasons=reasons,
                    source_identity=source_identity,
                    dimensions=dimensions,
                )
            )
    return tuple(facts)


def build_distributions(
    outcomes: Sequence[SubjectOutcomeFact],
    *,
    specification: AuditSpecification,
    cohort_start: date,
    as_of_date: date,
) -> tuple[DistributionFact, ...]:
    mature = [item for item in outcomes if item.maturity_status == "mature"]
    facts: list[DistributionFact] = []
    cohorts = tuple(
        cast(EvidenceCohort, item)
        for item in ("strict", "quality_stratified", "invalid")
    )
    for definition in specification.outcome_definitions:
        outcome_items = [
            item for item in mature if item.outcome_key == definition.outcome_key
        ]
        for cohort in cohorts:
            selected = [
                item
                for item in outcome_items
                if item.dimensions.get("evidence_cohort") == cohort
            ]
            if not selected:
                continue
            groups: list[tuple[str, Mapping[str, object], list[SubjectOutcomeFact]]] = [
                ("overall", {"evidence_cohort": cohort}, selected)
            ]
            for dimension in specification.group_dimensions:
                if dimension == "evidence_cohort":
                    continue
                values = sorted({str(item.dimensions.get(dimension)) for item in selected})
                groups.extend(
                    (
                        f"{dimension}.{_group_token(value)}",
                        {"evidence_cohort": cohort, dimension: value},
                        [
                            item
                            for item in selected
                            if str(item.dimensions.get(dimension)) == value
                        ],
                    )
                    for value in values
                )
            for group_key, dimensions, group in groups:
                values = pd.Series([item.value_number for item in group], dtype="float64")
                day_count = len({item.trade_date for item in group})
                facts.append(
                    DistributionFact(
                        cohort_start,
                        as_of_date,
                        cohort,
                        group_key,
                        definition.outcome_key,
                        definition.horizon,
                        len(group),
                        day_count,
                        "available" if day_count >= specification.minimum_ci_days else "insufficient_sample",
                        semantic_fingerprint(tuple(group)),
                        _distribution_statistics(values),
                        dimensions,
                    )
                )
    return tuple(facts)


def build_health_windows(
    days: Sequence[ReplayDayFact],
    outcomes: Sequence[SubjectOutcomeFact],
    *,
    specification: AuditSpecification,
) -> tuple[HealthWindowFact, ...]:
    ordered = sorted(days, key=lambda item: item.trade_date)
    facts: list[HealthWindowFact] = []
    for cohort in ("strict", "quality_stratified", "invalid"):
        cohort_days = [item for item in ordered if item.evidence_cohort == cohort]
        for window in specification.rolling_windows:
            for end_index in range(window - 1, len(cohort_days)):
                selected_days = cohort_days[end_index - window + 1 : end_index + 1]
                dates = {item.trade_date for item in selected_days}
                for definition in specification.outcome_definitions:
                    selected = [
                        item
                        for item in outcomes
                        if item.trade_date in dates
                        and item.outcome_key == definition.outcome_key
                        and item.maturity_status == "mature"
                    ]
                    values = pd.Series([item.value_number for item in selected], dtype="float64")
                    actual = len(selected_days)
                    facts.append(
                        HealthWindowFact(
                            selected_days[-1].trade_date,
                            window,
                            actual,
                            cast(EvidenceCohort, cohort),
                            "overall",
                            definition.outcome_key,
                            definition.horizon,
                            "available" if actual >= specification.minimum_ci_days else "insufficient_sample",
                            semantic_fingerprint((tuple(selected_days), tuple(selected))),
                            {
                                "candidate_day_rate": _mean(
                                    pd.Series([item.candidate_count > 0 for item in selected_days])
                                ),
                                "outcome_coverage_rate": len({item.trade_date for item in selected}) / actual,
                                "outcome_mean": _mean(values),
                                "outcome_p50": _quantile(values, 0.5),
                            },
                        )
                    )
    return tuple(facts)


def replay_day_fact(
    identity: AuditIdentity,
    replay: ReplayDayResult,
    parity: ProductionReplayParity,
) -> ReplayDayFact:
    generates = [item for item in replay.stages if item.attempt.stage_key == "generate"]
    primary = primary_generate_result(replay.stages)
    candidate_count = (
        len(candidate_handoff_from_output(cast(OpeningCandidateGenerateOutput, primary.rule_output)))
        if primary is not None
        else 0
    )
    return ReplayDayFact(
        identity,
        replay.trade_date,
        replay.status,
        replay.data_quality,
        evidence_cohort(replay.status, replay.data_quality),
        candidate_count,
        len(generates),
        len(replay.stages),
        replay.semantic_fingerprint,
        parity.day_stage_status(replay.trade_date),
        parity.day_input_status(replay.trade_date),
        None if primary is None else primary.attempt.cutoff_at,
        replay.errors,
    )


def replay_stage_fact(
    day: ReplayDayResult,
    stage,
    parity: ProductionReplayParity,
) -> ReplayStageFact:
    stage_parity = parity.stage(
        day.trade_date,
        stage.attempt.stage_key,
        stage.attempt.attempt_key,
    )
    return ReplayStageFact(
        day.trade_date,
        stage.attempt.stage_key,
        stage.attempt.attempt_key,
        stage.attempt.cutoff_at,
        stage.status,
        stage.data_quality,
        stage.typed_input_fingerprint,
        stage.rule_output_fingerprint,
        stage.clause_trace_fingerprint,
        "unavailable" if stage_parity is None else stage_parity.input_status,
        "unavailable" if stage_parity is None else stage_parity.output_status,
        "unavailable" if stage_parity is None else stage_parity.trace_status,
        {
            **dict(stage.rule_output.summary),
            "parity_reasons": [] if stage_parity is None else list(stage_parity.reasons),
        },
        {},
    )


def replay_input_fact(
    day: ReplayDayResult,
    stage,
    evidence,
    parity: ProductionReplayParity,
) -> ReplayInputFact:
    query = evidence.query
    stage_parity = parity.stage(
        day.trade_date,
        stage.attempt.stage_key,
        stage.attempt.attempt_key,
    )
    return ReplayInputFact(
        day.trade_date,
        stage.attempt.stage_key,
        stage.attempt.attempt_key,
        query.input_key,
        query.input_type,
        query.semantic_role,
        evidence.conformance.status,
        evidence.content.content_fingerprint,
        input_evidence_semantic_fingerprint(evidence),
        (
            "unavailable"
            if stage_parity is None
            else stage_parity.input_statuses.get(query.input_key, "unavailable")
        ),
        query.dataset_key,
        query.upstream_stage_key,
        query.upstream_attempt_key,
        asdict(query),
        tuple(asdict(item) for item in evidence.resolved_sources),
        asdict(evidence.content),
        evidence.conformance.reasons,
    )


def clause_fact(day: ReplayDayResult, stage, trace) -> ClauseObservationFact:
    return ClauseObservationFact(
        day.trade_date,
        stage.attempt.stage_key,
        stage.attempt.attempt_key,
        trace.clause_key,
        trace.clause_version,
        trace.subject_type,
        trace.subject_key,
        trace.evaluation_status,
        trace.data_quality,
        semantic_fingerprint(trace),
        trace.reason_codes,
        trace.inputs,
        trace.output,
    )


def evidence_cohort(status: str, quality: str) -> str:
    if status in {"invalid_input", "evaluator_error"} or quality == "missing":
        return "invalid"
    return "strict" if quality == "normal" else "quality_stratified"


def outcome_source_identity(bundle: ResolvedOutcomeBundle) -> Mapping[str, object]:
    return {
        item.requirement_key: item.content_evidence.content_fingerprint
        for item in bundle.inputs
    }


def _outcome_requirement(
    input_key: str,
    trade_date: date,
    dataset_key: str,
    date_start: date,
    date_end: date,
    *,
    fields: tuple[str, ...],
    filters: Mapping[str, object],
    symbols: tuple[str, ...] = (),
) -> OutcomeRequirement:
    canonical_symbols = tuple(dict.fromkeys(symbols))
    return OutcomeRequirement(
        input_key,
        trade_date,
        QueryIntent(
            input_key,
            "dataset",
            {"date_start": date_start, "date_end": date_end},
            semantic_role="annotation",
            dataset_key=dataset_key,
            fields=fields,
            filters=dict(filters),
            symbol_count=len(canonical_symbols),
            symbol_set_fingerprint=(
                semantic_fingerprint(tuple(sorted(canonical_symbols)))
                if canonical_symbols
                else None
            ),
            missing_policy="allow_empty",
        ),
        canonical_symbols,
    )


def _enrich_candidate_row(
    row: dict[str, object],
    *,
    daily: pd.DataFrame,
    window: pd.DataFrame,
    minute: pd.DataFrame,
    horizons: Mapping[date, Mapping[int, date | None]],
) -> dict[str, object]:
    trade_date = pd.Timestamp(row["trade_date"]).date()
    symbol = str(row["candidate_key"])
    reference = _number(row.get("candidate_reference_price"))
    cutoff = pd.Timestamp(row["candidate_cutoff_at"])
    same_day = daily[(daily["trade_date"] == trade_date) & (daily["symbol"] == symbol)]
    minute_after = minute[
        (minute["trade_date"] == trade_date)
        & (minute["symbol"] == symbol)
        & (minute["quote_time"] >= cutoff)
    ]
    window_after = window[
        (window["trade_date"] == trade_date)
        & (window["symbol"] == symbol)
        & (window["snapshot_at"] >= cutoff)
    ]
    if not minute_after.empty:
        peak = _series_number(minute_after["high_price"], "max")
        drawdown = _series_number(minute_after["low_price"], "min")
        intraday_source = "minute"
    elif not window_after.empty:
        peak = _series_number(window_after["last_price"], "max")
        drawdown = _series_number(window_after["last_price"], "min")
        intraday_source = "window_last_price"
    else:
        peak = drawdown = None
        intraday_source = "unavailable"
    close = _first_number(same_day, "close_price")
    row.update(
        {
            "t_close_return": _return(close, reference),
            "t_peak_return": _return(peak, reference),
            "t_drawdown_return": _return(drawdown, reference),
            "t_close_retention": _return(close, peak),
            "reference_available": reference is not None,
            "intraday_outcome_source": intraday_source,
        }
    )
    for horizon in (1, 3, 5):
        target = horizons.get(trade_date, {}).get(horizon)
        quote = daily[(daily["trade_date"] == target) & (daily["symbol"] == symbol)]
        row[f"t{horizon}_trade_date"] = target
        if horizon == 1:
            open_price = _first_number(quote, "open_price")
            row["t1_open_return"] = _return(open_price, reference)
            row["t1_open_at_up_limit"] = _same_price(
                open_price, _first_number(quote, "up_limit_price")
            )
            row["t1_open_at_down_limit"] = _same_price(
                open_price, _first_number(quote, "down_limit_price")
            )
        row[f"t{horizon}_close_return"] = _return(
            _first_number(quote, "close_price"), reference
        )
        row[f"t{horizon}_price_available"] = not quote.empty
    reasons = _outcome_quality_reasons(row)
    row["outcome_data_quality"] = "normal" if not reasons else "partial"
    row["outcome_quality_reasons"] = reasons
    return row


def _normalize_daily(frame: pd.DataFrame) -> pd.DataFrame:
    output = frame.copy()
    if output.empty:
        return pd.DataFrame(columns=("trade_date", "symbol", "open_price", "close_price"))
    output["trade_date"] = pd.to_datetime(output["trade_date"]).dt.date
    output["symbol"] = output["symbol"].astype(str)
    return output


def _normalize_intraday(frame: pd.DataFrame, timestamp: str) -> pd.DataFrame:
    output = frame.copy()
    if output.empty:
        columns = ("high_price", "low_price") if timestamp == "quote_time" else ("last_price",)
        return pd.DataFrame(columns=("trade_date", timestamp, "symbol", *columns))
    output["trade_date"] = pd.to_datetime(output["trade_date"]).dt.date
    output["symbol"] = output["symbol"].astype(str)
    output[timestamp] = pd.to_datetime(output[timestamp])
    return output


def _target_date(row: Mapping[str, object], trade_date: date, horizon: str) -> date | None:
    if horizon == "T":
        return trade_date
    value = row.get(f"t{int(horizon[2:])}_trade_date")
    return None if value is None or pd.isna(value) else pd.Timestamp(value).date()


def _distribution_statistics(values: pd.Series) -> Mapping[str, object]:
    numeric = pd.to_numeric(values, errors="coerce").dropna()
    return {
        "mean": _mean(numeric),
        "stddev": _number(numeric.std(ddof=1)),
        "p10": _quantile(numeric, 0.10),
        "p25": _quantile(numeric, 0.25),
        "p50": _quantile(numeric, 0.50),
        "p75": _quantile(numeric, 0.75),
        "p90": _quantile(numeric, 0.90),
        "p95": _quantile(numeric, 0.95),
        "win_rate": _mean(numeric > 0),
    }


def _first_number(frame: pd.DataFrame, column: str) -> float | None:
    return None if frame.empty or column not in frame else _number(frame.iloc[0][column])


def _series_number(series: pd.Series, operation: str) -> float | None:
    numeric = pd.to_numeric(series, errors="coerce").dropna()
    if numeric.empty:
        return None
    return float(numeric.max() if operation == "max" else numeric.min())


def _return(value: float | None, reference: float | None) -> float | None:
    if value is None or reference is None or reference <= 0:
        return None
    return value / reference - 1.0


def _same_price(
    value: float | None,
    limit: float | None,
    *,
    tolerance: float = 0.0001,
) -> bool | None:
    if value is None or limit is None or limit <= 0:
        return None
    return abs(value / limit - 1.0) <= tolerance


def _outcome_quality_reasons(row: Mapping[str, object]) -> tuple[str, ...]:
    reasons: list[str] = []
    if not row.get("reference_available"):
        reasons.append("reference_unavailable")
    if row.get("intraday_outcome_source") == "unavailable":
        reasons.append("post_cutoff_intraday_unavailable")
    for horizon in (1, 3, 5):
        if not row.get(f"t{horizon}_price_available"):
            reasons.append(f"t{horizon}_price_unavailable")
    return tuple(reasons)


def _mean(values: pd.Series) -> float | None:
    return _number(values.mean()) if not values.empty else None


def _quantile(values: pd.Series, quantile: float) -> float | None:
    return _number(values.quantile(quantile)) if not values.empty else None


def _number(value: object) -> float | None:
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return None if pd.isna(numeric) else float(numeric)


def _json_scalar(value: object) -> object:
    return None if value is None or pd.isna(value) else value


def _group_token(value: object) -> str:
    text = str(value).strip().lower()
    normalized = "".join(character if character.isalnum() else "_" for character in text)
    return normalized.strip("_") or "null"
