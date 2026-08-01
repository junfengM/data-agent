from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ValidationResult:
    gate_id: str
    passed: bool
    message: str
    severity: str = "warning"
    details: dict[str, Any] | None = None
    fix_hint: str | None = None
    owner_layer: str | None = None
    related_block_ids: list[str] = field(default_factory=list)
    related_evidence_ids: list[str] = field(default_factory=list)
    can_auto_repair: bool = False
