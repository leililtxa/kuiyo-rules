from __future__ import annotations

import pandas as pd

from kuiyo_rules.quality import frame_result_data_quality, materialized_data_quality


def test_materialized_quality_turns_missing_input_into_partial_artifact() -> None:
    assert materialized_data_quality(["normal", "missing"]) == "partial"
    assert materialized_data_quality(["partial", "missing"]) == "partial"
    assert materialized_data_quality(["proxy"]) == "proxy"


def test_frame_result_quality_distinguishes_all_and_partial_missing() -> None:
    assert frame_result_data_quality(pd.DataFrame()) == "missing"
    assert frame_result_data_quality(pd.DataFrame({"data_quality": ["missing", "missing"]})) == "missing"
    assert frame_result_data_quality(pd.DataFrame({"data_quality": ["normal", "missing"]})) == "partial"
    assert frame_result_data_quality(pd.DataFrame({"data_quality": ["proxy", "missing"]})) == "partial"
    assert frame_result_data_quality(pd.DataFrame({"data_quality": ["normal", "proxy"]})) == "proxy"
    assert frame_result_data_quality(pd.DataFrame({"data_quality": ["normal", "degraded"]})) == "degraded"
