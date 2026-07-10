from __future__ import annotations

from collections import Counter

import pandas as pd

from kuiyo_rules.contracts import CandidateTierInput, CandidateTierOutput
from kuiyo_rules.definitions import ResearchRuleVersion
from kuiyo_rules.evaluation.opening_candidate.generate import rule_identity
from kuiyo_rules.evaluation.opening_candidate.parameters import tier_parameters
from kuiyo_rules.evaluation.opening_candidate.tier_features import build_watch_tier_features
from kuiyo_rules.evaluation.opening_candidate.tier_rules import apply_watch_tiers
from kuiyo_rules.quality import frame_data_quality


def tier_opening_candidates(
    *,
    rule_version: ResearchRuleVersion,
    rule_input: CandidateTierInput,
) -> CandidateTierOutput:
    if rule_input.evaluations.empty:
        return CandidateTierOutput(
            status="upstream_no_evaluation",
            data_quality="missing",
            tiers=pd.DataFrame(),
            summary={
                "candidate_count": int(len(rule_input.candidates)),
                "evaluation_count": 0,
                "rule": rule_identity(rule_version),
            },
        )
    parameters = tier_parameters(rule_version)
    features = build_watch_tier_features(
        candidates=rule_input.candidates,
        evaluations=rule_input.evaluations,
        parameters=parameters,
    )
    tiers = apply_watch_tiers(features)
    counts = Counter(str(value) for value in tiers["watch_level"])
    return CandidateTierOutput(
        status="ok",
        data_quality=frame_data_quality(tiers),
        tiers=tiers,
        summary={
            "candidate_count": int(len(rule_input.candidates)),
            "evaluation_count": int(len(rule_input.evaluations)),
            "watch_level_counts": dict(counts),
            "rule": rule_identity(rule_version),
        },
    )
