from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Mapping

from kuiyo_rules.identifiers import require_key, require_version
from kuiyo_rules.serialization import FrozenJson, freeze_json, thaw_json


ClauseType = Literal["decision", "invariant"]


@dataclass(frozen=True)
class RuleClauseReference:
    clause_key: str
    clause_version: str
    clause_type: ClauseType
    source_refs: tuple[str, ...]
    parameters: Mapping[str, FrozenJson] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_key(self.clause_key, field="clause_key")
        require_version(self.clause_version, field="clause_version")
        if self.clause_type not in {"decision", "invariant"}:
            raise ValueError(f"unsupported clause_type: {self.clause_type}")
        if not self.source_refs:
            raise ValueError("source_refs must not be empty")
        if any(not item.strip() for item in self.source_refs):
            raise ValueError("source_refs must not contain empty values")
        object.__setattr__(self, "source_refs", tuple(self.source_refs))
        frozen = freeze_json(self.parameters, path=f"clause[{self.clause_key}].parameters")
        if not isinstance(frozen, Mapping):
            raise TypeError("parameters must be an object")
        object.__setattr__(self, "parameters", frozen)

    def to_payload(self) -> dict[str, object]:
        return {
            "clause_key": self.clause_key,
            "clause_version": self.clause_version,
            "clause_type": self.clause_type,
            "source_refs": list(self.source_refs),
            "parameters": thaw_json(self.parameters),
        }
