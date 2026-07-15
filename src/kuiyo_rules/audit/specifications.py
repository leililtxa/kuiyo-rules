from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal

from kuiyo_rules.audit.identifiers import require_audit_spec_key
from kuiyo_rules.identifiers import require_key, require_version
from kuiyo_rules.serialization import FrozenJson, definition_hash, freeze_json, thaw_json


OutcomeValueType = Literal["number", "boolean", "text"]


@dataclass(frozen=True)
class OutcomeDefinition:
    outcome_key: str
    horizon: str
    reference_key: str
    value_type: OutcomeValueType
    executable: bool

    def __post_init__(self) -> None:
        require_key(self.outcome_key, field="outcome_key")
        require_key(self.reference_key, field="reference_key")
        if not self.horizon.strip():
            raise ValueError("horizon must not be empty")
        if self.value_type not in {"number", "boolean", "text"}:
            raise ValueError(f"unsupported outcome value_type: {self.value_type}")

    def to_payload(self) -> dict[str, object]:
        return {
            "outcome_key": self.outcome_key,
            "horizon": self.horizon,
            "reference_key": self.reference_key,
            "value_type": self.value_type,
            "executable": self.executable,
        }


@dataclass(frozen=True)
class AuditSpecification:
    audit_spec_key: str
    audit_spec_version: str
    target_rule_key: str
    supported_rule_versions: tuple[str, ...]
    outcome_definitions: tuple[OutcomeDefinition, ...]
    group_dimensions: tuple[str, ...]
    rolling_windows: tuple[int, ...] = (5, 10, 20)
    minimum_ci_days: int = 20
    metadata: Mapping[str, FrozenJson] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_audit_spec_key(self.audit_spec_key)
        require_version(self.audit_spec_version, field="audit_spec_version")
        require_key(self.target_rule_key, field="target_rule_key")
        if not self.supported_rule_versions:
            raise ValueError("supported_rule_versions must not be empty")
        for version in self.supported_rule_versions:
            require_version(version, field="supported_rule_versions")
        if not self.outcome_definitions:
            raise ValueError("outcome_definitions must not be empty")
        if len({item.outcome_key for item in self.outcome_definitions}) != len(
            self.outcome_definitions
        ):
            raise ValueError("outcome definitions must have unique outcome_key values")
        for dimension in self.group_dimensions:
            require_key(dimension, field="group_dimensions")
        if any(window <= 0 for window in self.rolling_windows):
            raise ValueError("rolling_windows must contain positive values")
        if self.minimum_ci_days <= 0:
            raise ValueError("minimum_ci_days must be positive")
        metadata = freeze_json(self.metadata, path="metadata")
        if not isinstance(metadata, Mapping):
            raise TypeError("metadata must be an object")
        object.__setattr__(self, "supported_rule_versions", tuple(self.supported_rule_versions))
        object.__setattr__(self, "outcome_definitions", tuple(self.outcome_definitions))
        object.__setattr__(self, "group_dimensions", tuple(self.group_dimensions))
        object.__setattr__(self, "rolling_windows", tuple(self.rolling_windows))
        object.__setattr__(self, "metadata", metadata)

    @property
    def definition_hash(self) -> str:
        return definition_hash(freeze_json(self.definition_payload()))

    def definition_payload(self) -> dict[str, object]:
        return {
            "audit_spec_key": self.audit_spec_key,
            "audit_spec_version": self.audit_spec_version,
            "target_rule_key": self.target_rule_key,
            "supported_rule_versions": list(self.supported_rule_versions),
            "outcome_definitions": [item.to_payload() for item in self.outcome_definitions],
            "group_dimensions": list(self.group_dimensions),
            "rolling_windows": list(self.rolling_windows),
            "minimum_ci_days": self.minimum_ci_days,
            "metadata": thaw_json(self.metadata),
        }
