from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from kuiyo_rules import canonical_attempt_key


def test_canonical_attempt_key_uses_decision_cutoff() -> None:
    cutoff = datetime(2026, 7, 3, 9, 41, tzinfo=ZoneInfo("Asia/Shanghai"))

    assert canonical_attempt_key("evaluate", cutoff) == "evaluate.0941"


def test_canonical_attempt_key_rejects_naive_cutoff() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        canonical_attempt_key("evaluate", datetime(2026, 7, 3, 9, 41))


def test_canonical_attempt_key_rejects_empty_stage() -> None:
    cutoff = datetime(2026, 7, 3, 9, 41, tzinfo=ZoneInfo("Asia/Shanghai"))

    with pytest.raises(ValueError, match="stage_key"):
        canonical_attempt_key(" ", cutoff)
