from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from kuiyo_rules.replay import (
    ReplayDayPlan,
    ReplayPlan,
    ReplayRequest,
    ReplayStageAttempt,
    ResolvedInputBundle,
    ResolvedStageInput,
)


HASH = "a" * 64
TZ = ZoneInfo("Asia/Shanghai")


@dataclass(frozen=True)
class FakeInput:
    trade_date: date


def attempt(day: date, *, stage: str = "generate", key: str = "generate.0936"):
    return ReplayStageAttempt(
        stage_key=stage,
        attempt_key=key,
        cutoff_at=datetime(day.year, day.month, day.day, 9, 36, tzinfo=TZ),
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


def test_resolved_bundle_rejects_wrong_trade_date() -> None:
    day = date(2026, 7, 14)
    with pytest.raises(ValueError, match="match attempt"):
        ResolvedStageInput(attempt(day), FakeInput(date(2026, 7, 15)), ())


def test_resolved_bundle_requires_unique_attempt_identity() -> None:
    day = date(2026, 7, 14)
    resolved = ResolvedStageInput(attempt(day), FakeInput(day), ())
    with pytest.raises(ValueError, match="unique stage/attempt"):
        ResolvedInputBundle(
            "opening_candidate_watch",
            "v001",
            HASH,
            day,
            (resolved, resolved),
        )
