from __future__ import annotations

import re


AUDIT_SPEC_KEY_PATTERN = re.compile(r"^AUDIT-[0-9]{3}$")


def require_audit_spec_key(value: str, *, field: str = "audit_spec_key") -> str:
    if not AUDIT_SPEC_KEY_PATTERN.fullmatch(value):
        raise ValueError(
            f"{field} must match {AUDIT_SPEC_KEY_PATTERN.pattern}: {value!r}"
        )
    return value
