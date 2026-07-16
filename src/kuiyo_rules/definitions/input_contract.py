from __future__ import annotations

from kuiyo_rules.definitions.models import ResearchRuleVersion


def rule_input_text(version: ResearchRuleVersion, key: str) -> str:
    value = version.input_contract.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"invalid rule input contract value: {key}")
    return value


def rule_input_int(version: ResearchRuleVersion, key: str) -> int:
    value = version.input_contract.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"invalid rule input contract value: {key}")
    return int(value)


def rule_input_strings(version: ResearchRuleVersion, key: str) -> tuple[str, ...]:
    value = version.input_contract.get(key)
    if not isinstance(value, tuple) or not value:
        raise ValueError(f"invalid rule input contract value: {key}")
    return tuple(str(item) for item in value)
