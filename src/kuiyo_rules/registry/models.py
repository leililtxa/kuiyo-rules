from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping

from kuiyo_rules.definitions.models import ResearchRuleDefinition, ResearchRuleVersion
from kuiyo_rules.identifiers import require_key, require_version


@dataclass(frozen=True)
class RuleStageSpec:
    stage_key: str
    input_contract_key: str
    input_contract_version: str
    output_contract_key: str
    output_contract_version: str
    input_type: type[Any]
    output_type: type[Any]

    def __post_init__(self) -> None:
        require_key(self.stage_key, field="stage_key")
        require_key(self.input_contract_key, field="input_contract_key")
        require_key(self.output_contract_key, field="output_contract_key")
        require_version(self.input_contract_version, field="input_contract_version")
        require_version(self.output_contract_version, field="output_contract_version")


@dataclass(frozen=True)
class RuleSpec:
    definition: ResearchRuleDefinition
    versions: Mapping[str, ResearchRuleVersion]
    stages: Mapping[str, RuleStageSpec]

    def __post_init__(self) -> None:
        versions = dict(self.versions)
        stages = dict(self.stages)
        if not versions:
            raise ValueError("versions must not be empty")
        if not stages:
            raise ValueError("stages must not be empty")
        for version_key, version in versions.items():
            if version_key != version.rule_version:
                raise ValueError(f"version mapping key mismatch: {version_key}")
            if version.rule_key != self.definition.rule_key:
                raise ValueError(f"version rule_key mismatch: {version.rule_key}")
        for stage_key, stage in stages.items():
            if stage_key != stage.stage_key:
                raise ValueError(f"stage mapping key mismatch: {stage_key}")
        object.__setattr__(self, "versions", MappingProxyType(versions))
        object.__setattr__(self, "stages", MappingProxyType(stages))

