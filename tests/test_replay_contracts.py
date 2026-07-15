from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from kuiyo_rules.evidence import (
    ContentEvidence,
    DatasetQueryRequirement,
    InputEvidence,
    KnownTimeConformance,
    QueryIntent,
)
from kuiyo_rules.replay import (
    ReplayDayPlan,
    ReplayPlan,
    ReplayProgress,
    ReplayRequest,
    ReplayStageAttempt,
    ReplayStageInputPlan,
    ReplayStageResult,
    ResolvedReplayDataset,
    ResolvedReplayStageData,
)


HASH = "a" * 64
TZ = ZoneInfo("Asia/Shanghai")


@dataclass(frozen=True)
class FakeOutput:
    status: str = "ok"
    data_quality: str = "normal"
    summary: dict[str, object] = field(default_factory=dict)
    clause_traces: tuple = ()


def attempt(
    day: date,
    *,
    stage: str = "generate",
    key: str = "generate.0936",
    hour: int = 9,
    minute: int = 36,
) -> ReplayStageAttempt:
    return ReplayStageAttempt(
        stage_key=stage,
        attempt_key=key,
        cutoff_at=datetime(day.year, day.month, day.day, hour, minute, tzinfo=TZ),
    )


def stage_result(item: ReplayStageAttempt) -> ReplayStageResult:
    return ReplayStageResult(item, "completed", "normal", FakeOutput(), (), ())


def dataset_query(input_key: str = "generate.stock_quotes") -> QueryIntent:
    return QueryIntent(
        input_key=input_key,
        input_type="dataset",
        requested_range={"start": "2026-07-14", "end": "2026-07-14"},
        dataset_key="market.stock.quote.window",
    )


def dataset_requirement(input_key: str = "generate.stock_quotes") -> DatasetQueryRequirement:
    return DatasetQueryRequirement(dataset_query(input_key))


def dataset_evidence(query: QueryIntent) -> InputEvidence:
    return InputEvidence(
        query=query,
        resolved_sources=(),
        content=ContentEvidence(
            row_count=1,
            entity_count=1,
            observation_count=1,
            content_fingerprint="b" * 64,
            max_known_at="2026-07-14T09:35:59+08:00",
            quality="normal",
            quality_reasons=(),
        ),
        conformance=KnownTimeConformance(
            decision_cutoff_at=datetime(2026, 7, 14, 9, 36, tzinfo=TZ),
            capture_mode="historical_reconstruction",
            captured_at=datetime(2026, 7, 15, 19, 0, tzinfo=TZ),
            temporal_capability="point_in_time",
            status="valid",
        ),
    )


def test_replay_plan_preserves_canonical_identity() -> None:
    day = date(2026, 7, 14)
    request = ReplayRequest("opening_candidate_watch", "v001", (day,))
    plan = ReplayPlan(
        request.rule_key,
        request.rule_version,
        HASH,
        (ReplayDayPlan(day, "Asia/Shanghai", (attempt(day),)),),
    )

    assert plan.rule_definition_hash == HASH
    assert plan.days[0].attempts[0].attempt_key == "generate.0936"


def test_replay_request_rejects_duplicate_dates() -> None:
    day = date(2026, 7, 14)
    with pytest.raises(ValueError, match="duplicates"):
        ReplayRequest("opening_candidate_watch", "v001", (day, day))


def test_replay_attempt_requires_timezone() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        ReplayStageAttempt(
            "generate",
            "generate.0936",
            datetime(2026, 7, 14, 9, 36),
        )


def test_replay_progress_advances_in_planned_order() -> None:
    day = date(2026, 7, 14)
    generate = attempt(day)
    evaluate = attempt(
        day,
        stage="evaluate",
        key="evaluate.0946",
        minute=46,
    )
    progress = ReplayProgress(
        ReplayDayPlan(day, "Asia/Shanghai", (generate, evaluate)),
        processed_attempt_count=0,
    )

    assert progress.next_attempt == generate
    progress = progress.advance(stage_result(generate))
    assert progress.next_attempt == evaluate
    progress = progress.advance(stage_result(evaluate))
    assert progress.is_complete
    assert progress.next_attempt is None

    with pytest.raises(ValueError, match="completed replay"):
        progress.advance(stage_result(evaluate))


def test_replay_progress_rejects_skipped_stage() -> None:
    day = date(2026, 7, 14)
    generate = attempt(day)
    evaluate = attempt(
        day,
        stage="evaluate",
        key="evaluate.0946",
        minute=46,
    )
    progress = ReplayProgress(
        ReplayDayPlan(day, "Asia/Shanghai", (generate, evaluate)),
        processed_attempt_count=0,
    )

    with pytest.raises(ValueError, match="next planned"):
        progress.advance(stage_result(evaluate))


def test_replay_progress_can_skip_a_conditional_attempt_without_fake_output() -> None:
    day = date(2026, 7, 14)
    first = attempt(day)
    second = attempt(day, key="generate.0937", minute=37)
    evaluate = attempt(day, stage="evaluate", key="evaluate.0946", minute=46)
    progress = ReplayProgress(
        ReplayDayPlan(day, "Asia/Shanghai", (first, second, evaluate)),
        processed_attempt_count=0,
    )

    progress = progress.advance(stage_result(first)).skip_next()

    assert progress.next_attempt == evaluate
    assert progress.completed_stages == (stage_result(first),)


def test_resolved_stage_data_must_match_external_requirements() -> None:
    day = date(2026, 7, 14)
    query = dataset_query()
    plan = ReplayStageInputPlan(
        "opening_candidate_watch",
        "v001",
        HASH,
        day,
        attempt(day),
        (DatasetQueryRequirement(query),),
    )
    resolved = ResolvedReplayDataset(
        query.input_key,
        pd.DataFrame([{"symbol": "600573.SH"}]),
        dataset_evidence(query),
    )

    bundle = ResolvedReplayStageData(plan, (resolved,))
    assert bundle.datasets[0].input_key == query.input_key

    with pytest.raises(ValueError, match="exactly match"):
        ResolvedReplayStageData(plan, ())


def test_stage_input_plan_separates_dataset_and_upstream_requirements() -> None:
    day = date(2026, 7, 14)
    external = dataset_requirement()
    upstream = QueryIntent(
        input_key="evaluate.candidates",
        input_type="stage_output",
        requested_range={},
        upstream_stage_key="generate",
        upstream_attempt_key="generate.0936",
        upstream_output_contract="opening_candidate.generate.output/v001",
        upstream_content_fingerprint="c" * 64,
    )
    plan = ReplayStageInputPlan(
        "opening_candidate_watch",
        "v001",
        HASH,
        day,
        attempt(day),
        (external, upstream),
    )

    assert plan.external_requirements == (external,)
    assert plan.upstream_requirements == (upstream,)
