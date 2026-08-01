from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class MetricEntry:
    name: str
    formula: str
    grain: str = ""
    dimensions: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    caveat: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class DimensionEntry:
    name: str
    source_column: str = ""
    source_table: str = ""
    description: str = ""


@dataclass
class CaveatEntry:
    description: str
    severity: str = "info"  # info, warning, critical
    affected_metrics: list[str] = field(default_factory=list)
    source: str = ""
