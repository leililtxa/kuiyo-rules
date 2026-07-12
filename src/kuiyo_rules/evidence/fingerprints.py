from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import pandas as pd

from kuiyo_rules.evidence.contracts import InputEvidence


def semantic_fingerprint(value: Any) -> str:
    payload = json.dumps(
        canonical_value(value),
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def dataframe_fingerprint(frame: pd.DataFrame) -> str:
    return semantic_fingerprint(frame)


def typed_rule_contract_fingerprint(value: object) -> str:
    if not hasattr(value, "__dataclass_fields__"):
        raise TypeError("typed rule contract must be a dataclass instance")
    return semantic_fingerprint(value)


def input_evidence_semantic_payload(evidence: InputEvidence) -> dict[str, object]:
    query = evidence.query
    return {
        "input_key": query.input_key,
        "input_type": query.input_type,
        "semantic_role": query.semantic_role,
        "dataset_key": query.dataset_key,
        "requested_range": query.requested_range,
        "fields": query.fields,
        "filters": query.filters,
        "symbol_count": query.symbol_count,
        "symbol_set_fingerprint": query.symbol_set_fingerprint,
        "missing_policy": query.missing_policy,
        "upstream_stage_key": query.upstream_stage_key,
        "upstream_attempt_key": query.upstream_attempt_key,
        "upstream_output_contract": query.upstream_output_contract,
        "upstream_content_fingerprint": query.upstream_content_fingerprint,
        "content_fingerprint": evidence.content.content_fingerprint,
        "min_known_at": evidence.content.min_known_at,
        "max_known_at": evidence.content.max_known_at,
        "conformance_status": evidence.conformance.status,
        "conformance_reasons": evidence.conformance.reasons,
        "temporal_capability": evidence.conformance.temporal_capability,
    }


def input_evidence_semantic_fingerprint(evidence: InputEvidence) -> str:
    return semantic_fingerprint(input_evidence_semantic_payload(evidence))


def canonical_value(value: Any) -> Any:
    if isinstance(value, pd.DataFrame):
        columns = sorted(str(column) for column in value.columns)
        normalized = value.rename(columns={column: str(column) for column in value.columns})
        normalized = normalized.reindex(columns=columns)
        rows = [
            {column: canonical_value(row[column]) for column in columns}
            for row in normalized.to_dict(orient="records")
        ]
        rows.sort(key=lambda row: json.dumps(row, sort_keys=True, separators=(",", ":")))
        return {"columns": columns, "rows": rows}
    if isinstance(value, Mapping):
        return {str(key): canonical_value(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [canonical_value(item) for item in value]
    if isinstance(value, (date, datetime, pd.Timestamp)):
        return value.isoformat()
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, Decimal):
        return {"decimal": format(value.normalize(), "f")}
    if isinstance(value, float):
        return None if not math.isfinite(value) else value
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item"):
        return canonical_value(value.item())
    if hasattr(value, "to_payload"):
        return canonical_value(value.to_payload())
    if hasattr(value, "__dataclass_fields__"):
        return {
            field_name: canonical_value(getattr(value, field_name))
            for field_name in value.__dataclass_fields__
        }
    raise TypeError(f"unsupported fingerprint value: {type(value).__name__}")
