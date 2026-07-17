from __future__ import annotations

from collections.abc import Mapping, Sequence

from kuiyo_rules.audit.specifications import AuditSpecification


class AuditSpecificationRegistry:
    def __init__(self, specifications: Sequence[AuditSpecification]) -> None:
        mapping = {
            (item.audit_spec_key, item.audit_spec_version): item
            for item in specifications
        }
        if len(mapping) != len(specifications):
            raise ValueError("duplicate AuditSpecification identity")
        self._specifications: Mapping[tuple[str, str], AuditSpecification] = mapping

    def get(self, audit_spec_key: str, audit_spec_version: str) -> AuditSpecification:
        try:
            return self._specifications[(audit_spec_key, audit_spec_version)]
        except KeyError as exc:
            raise KeyError(
                f"unknown audit specification: {audit_spec_key}/{audit_spec_version}"
            ) from exc
