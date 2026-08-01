"""Helpers for treating manifest/snapshot artifacts as the primary visual report.

visual_report is the product-facing artifact type: a single readable report
composed from markdown, charts, tables, cards, sources, and a data snapshot.
"""
from __future__ import annotations

from app.models.schemas import Artifact, ArtifactType


def find_visual_report_artifact(artifacts: list[Artifact]) -> Artifact | None:
    """Return the primary visual-report artifact."""
    for artifact in artifacts:
        if artifact.type == ArtifactType.visual_report:
            return artifact
    return None
