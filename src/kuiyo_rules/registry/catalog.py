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
from kuiyo_rules.evaluation import (
    evaluate_opening_candidates,
    generate_opening_candidates,
    tier_opening_candidates,
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
            evaluator=generate_opening_candidates,
        ),
        "evaluate": RuleStageSpec(
            stage_key="evaluate",
            input_contract_key="opening_candidate.evaluate.input",
            input_contract_version="v001",
            output_contract_key="opening_candidate.evaluate.output",
            output_contract_version="v001",
            input_type=CandidateEvaluationInput,
            output_type=CandidateEvaluationOutput,
            evaluator=evaluate_opening_candidates,
        ),
        "tier": RuleStageSpec(
            stage_key="tier",
            input_contract_key="opening_candidate.tier.input",
            input_contract_version="v001",
            output_contract_key="opening_candidate.tier.output",
            output_contract_version="v001",
            input_type=CandidateTierInput,
            output_type=CandidateTierOutput,
            evaluator=tier_opening_candidates,
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


def evaluate_rule(
    *,
    rule_key: str,
    rule_version: str,
    stage_key: str,
    rule_input: object,
) -> object:
    spec = get_rule_spec(rule_key)
    version = get_rule_version(rule_key, rule_version)
    try:
        stage = spec.stages[stage_key]
    except KeyError as exc:
        raise KeyError(f"unknown rule stage: {rule_key}/{stage_key}") from exc
    if not isinstance(rule_input, stage.input_type):
        raise TypeError(
            f"invalid input for {rule_key}/{stage_key}: "
            f"expected {stage.input_type.__name__}, got {type(rule_input).__name__}"
        )
    output = stage.evaluator(rule_version=version, rule_input=rule_input)
    if not isinstance(output, stage.output_type):
        raise TypeError(
            f"invalid output for {rule_key}/{stage_key}: "
            f"expected {stage.output_type.__name__}, got {type(output).__name__}"
        )
    return output
