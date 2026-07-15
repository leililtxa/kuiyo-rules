from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal


InputType = Literal["dataset", "stage_output"]
InputSemanticRole = Literal["decision", "runtime_reference", "annotation"]
CaptureMode = Literal["contemporaneous_capture", "historical_reconstruction"]
TemporalCapability = Literal["point_in_time", "current_snapshot", "unknown"]
ConformanceStatus = Literal["valid", "degraded", "invalid"]


@dataclass(frozen=True)
class QueryIntent:
    input_key: str
    input_type: InputType
    requested_range: dict[str, object]
    semantic_role: InputSemanticRole = "decision"
    dataset_key: str | None = None
    fields: tuple[str, ...] = ()
    filters: dict[str, object] | None = None
    symbol_count: int = 0
    symbol_set_fingerprint: str | None = None
    missing_policy: str | None = None
    source_preference: str | None = None
    upstream_stage_key: str | None = None
    upstream_attempt_key: str | None = None
    upstream_output_contract: str | None = None
    upstream_content_fingerprint: str | None = None

    def __post_init__(self) -> None:
        if not self.input_key.strip():
            raise ValueError("input_key must not be empty")
        if self.input_type == "dataset" and not self.dataset_key:
            raise ValueError("dataset input requires dataset_key")
        if self.input_type == "stage_output" and not (
            self.upstream_stage_key
            and self.upstream_attempt_key
            and self.upstream_output_contract
            and self.upstream_content_fingerprint
        ):
            raise ValueError("stage_output input requires complete upstream identity")


@dataclass(frozen=True)
class DatasetQueryRequirement:
    query: QueryIntent
    symbols: tuple[str, ...] = ()
    allow_full_scan: bool = False

    def __post_init__(self) -> None:
        if self.query.input_type != "dataset":
            raise ValueError("Dataset query requirement requires Dataset QueryIntent")
        symbols = tuple(dict.fromkeys(str(item) for item in self.symbols))
        if any(not item for item in symbols):
            raise ValueError("Dataset query symbols must not contain empty values")
        if self.query.symbol_count != len(symbols):
            raise ValueError("query symbol_count must match resolution symbols")
        object.__setattr__(self, "symbols", symbols)


@dataclass(frozen=True)
class ResolvedSourceEvidence:
    storage_type: str
    location: str
    date_start: str | None
    date_end: str | None
    time_start: str | None
    time_end: str | None
    row_count: int
    entity_count: int
    observation_count: int
    source_status: str
    warning_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class ContentEvidence:
    row_count: int
    entity_count: int
    observation_count: int
    content_fingerprint: str
    max_known_at: str | None
    quality: str
    quality_reasons: tuple[str, ...]
    min_known_at: str | None = None
    effective_date_start: str | None = None
    effective_date_end: str | None = None
    effective_time_start: str | None = None
    effective_time_end: str | None = None


@dataclass(frozen=True)
class KnownTimeConformance:
    decision_cutoff_at: datetime
    capture_mode: CaptureMode
    captured_at: datetime
    temporal_capability: TemporalCapability
    status: ConformanceStatus
    reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for field_name in ("decision_cutoff_at", "captured_at"):
            value = getattr(self, field_name)
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{field_name} must be timezone-aware")


@dataclass(frozen=True)
class InputEvidence:
    query: QueryIntent
    resolved_sources: tuple[ResolvedSourceEvidence, ...]
    content: ContentEvidence
    conformance: KnownTimeConformance
