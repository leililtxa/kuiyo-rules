from __future__ import annotations

from types import MappingProxyType
from typing import Mapping

from kuiyo_rules.contracts.opening_candidate import (
    CandidateEvaluationInput,
    CandidateEvaluationOutput,
    CandidateTierInput,
    CandidateTierOutput,
    OpeningCandidateGenerateInput,
    OpeningCandidateGenerateOutput,
)
from kuiyo_rules.definitions.models import ResearchRuleVersion
from kuiyo_rules.definitions.opening_candidate import (
    OPENING_CANDIDATE_BASELINE_V001,
    OPENING_CANDIDATE_DEFINITION,
)
from kuiyo_rules.registry.models import RuleSpec, RuleStageSpec


OPENING_CANDIDATE_SPEC = RuleSpec(
    definition=OPENING_CANDIDATE_DEFINITION,
    versions={OPENING_CANDIDATE_BASELINE_V001.rule_version: OPENING_CANDIDATE_BASELINE_V001},
    stages={
        "generate": RuleStageSpec(
            stage_key="generate",
            input_contract_key="opening_candidate.generate.input",
            input_contract_version="v001",
            output_contract_key="opening_candidate.generate.output",
            output_contract_version="v001",
            input_type=OpeningCandidateGenerateInput,
            output_type=OpeningCandidateGenerateOutput,
        ),
        "evaluate": RuleStageSpec(
            stage_key="evaluate",
            input_contract_key="opening_candidate.evaluate.input",
            input_contract_version="v001",
            output_contract_key="opening_candidate.evaluate.output",
            output_contract_version="v001",
            input_type=CandidateEvaluationInput,
            output_type=CandidateEvaluationOutput,
        ),
        "tier": RuleStageSpec(
            stage_key="tier",
            input_contract_key="opening_candidate.tier.input",
            input_contract_version="v001",
            output_contract_key="opening_candidate.tier.output",
            output_contract_version="v001",
            input_type=CandidateTierInput,
            output_type=CandidateTierOutput,
        ),
    },
)


RULE_SPECS: Mapping[str, RuleSpec] = MappingProxyType(
    {OPENING_CANDIDATE_DEFINITION.rule_key: OPENING_CANDIDATE_SPEC}
)


def get_rule_spec(rule_key: str) -> RuleSpec:
    try:
        return RULE_SPECS[rule_key]
    except KeyError as exc:
        raise KeyError(f"unknown rule_key: {rule_key}") from exc


def get_rule_version(rule_key: str, rule_version: str) -> ResearchRuleVersion:
    spec = get_rule_spec(rule_key)
    try:
        return spec.versions[rule_version]
    except KeyError as exc:
        raise KeyError(f"unknown rule version: {rule_key}/{rule_version}") from exc

