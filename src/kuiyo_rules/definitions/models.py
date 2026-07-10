from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from kuiyo_rules.clauses.models import RuleClauseReference
from kuiyo_rules.identifiers import require_key, require_version
from kuiyo_rules.serialization import FrozenJson, definition_hash, freeze_json, thaw_json


DefinitionStatus = Literal["active", "deprecated"]
VersionStatus = Literal["proposed", "validated", "rejected"]
ProvenanceStatus = Literal["confirmed", "pending_review"]


@dataclass(frozen=True)
class ResearchRuleDefinition:
    rule_key: str
    name: str
    decision_purpose: str
    output_type: str
    input_contract_key: str
    output_contract_key: str
    status: DefinitionStatus = "active"
    description: str = ""

    def __post_init__(self) -> None:
        require_key(self.rule_key, field="rule_key")
        require_key(self.input_contract_key, field="input_contract_key")
        require_key(self.output_contract_key, field="output_contract_key")
        if not self.name.strip():
            raise ValueError("name must not be empty")
        if not self.decision_purpose.strip():
            raise ValueError("decision_purpose must not be empty")
        if not self.output_type.strip():
            raise ValueError("output_type must not be empty")
        if self.status not in {"active", "deprecated"}:
            raise ValueError(f"unsupported definition status: {self.status}")


@dataclass(frozen=True)
class ResearchRuleVersion:
    rule_key: str
    rule_version: str
    lifecycle_status: VersionStatus
    provenance_status: ProvenanceStatus
    input_contract_version: str
    output_contract_version: str
    decision_policy: Mapping[str, FrozenJson]
    known_time_contract: Mapping[str, FrozenJson]
    input_contract: Mapping[str, FrozenJson]
    clause_composition: tuple[RuleClauseReference, ...]
    output_contract: Mapping[str, FrozenJson]
    source_hypothesis_keys: tuple[str, ...]
    frozen_at: datetime
    metadata: Mapping[str, FrozenJson] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_key(self.rule_key, field="rule_key")
        require_version(self.rule_version, field="rule_version")
        require_version(self.input_contract_version, field="input_contract_version")
        require_version(self.output_contract_version, field="output_contract_version")
        if self.lifecycle_status not in {"proposed", "validated", "rejected"}:
            raise ValueError(f"unsupported lifecycle_status: {self.lifecycle_status}")
        if self.provenance_status not in {"confirmed", "pending_review"}:
            raise ValueError(f"unsupported provenance_status: {self.provenance_status}")
        if self.frozen_at.tzinfo is None or self.frozen_at.utcoffset() is None:
            raise ValueError("frozen_at must be timezone-aware")
        if not self.clause_composition:
            raise ValueError("clause_composition must not be empty")
        object.__setattr__(self, "clause_composition", tuple(self.clause_composition))
        object.__setattr__(self, "source_hypothesis_keys", tuple(self.source_hypothesis_keys))
        for field_name in (
            "decision_policy",
            "known_time_contract",
            "input_contract",
            "output_contract",
            "metadata",
        ):
            value = freeze_json(getattr(self, field_name), path=field_name)
            if not isinstance(value, Mapping):
                raise TypeError(f"{field_name} must be an object")
            object.__setattr__(self, field_name, value)

    @property
    def definition_hash(self) -> str:
        return definition_hash(freeze_json(self.definition_payload()))

    def definition_payload(self) -> dict[str, object]:
        return {
            "rule_key": self.rule_key,
            "rule_version": self.rule_version,
            "input_contract_version": self.input_contract_version,
            "output_contract_version": self.output_contract_version,
            "decision_policy": thaw_json(self.decision_policy),
            "known_time_contract": thaw_json(self.known_time_contract),
            "input_contract": thaw_json(self.input_contract),
            "clause_composition": [item.to_payload() for item in self.clause_composition],
            "output_contract": thaw_json(self.output_contract),
            "source_hypothesis_keys": list(self.source_hypothesis_keys),
        }
