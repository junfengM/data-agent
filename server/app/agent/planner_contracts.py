from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CandidateAnglePayload(BaseModel):
    question: str
    dimensions: list[str] = Field(default_factory=list)
    measures: list[str] = Field(default_factory=list)
    expected_evidence: str = ""
    impact_score: float = 0.0
    confidence_score: float = 0.0
    actionability_score: float = 0.0
    novelty_score: float = 0.0
    relevance_score: float = 0.0
    data_sufficiency_score: float = 0.0


class ChartSpecPayload(BaseModel):
    name: str = ""
    chart_type: str = ""
    title: str = ""
    x_field: str | None = None
    y_fields: list[str] = Field(default_factory=list)
    intent: str | None = None


class VisualPlanItemPayload(BaseModel):
    block_type: str
    source_section: str
    id: str | None = None
    source_ref: str | None = None
    title: str | None = None
    intent: str | None = None
    priority: str = "primary"
    options: dict[str, Any] = Field(default_factory=dict)


class PlannerFinalPayload(BaseModel):
    title: str
    summary: str = ""
    selected_skills: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)
    next_checks: list[str] = Field(default_factory=list)
    report_md: str
    analysis_intent: dict[str, Any] = Field(default_factory=dict)
    candidate_angles: list[CandidateAnglePayload] = Field(default_factory=list)
    chart_specs: list[ChartSpecPayload] = Field(default_factory=list)
    visual_plan: list[VisualPlanItemPayload] = Field(default_factory=list)
    feedback_evaluation: dict[str, Any] = Field(default_factory=dict)


def build_minimal_payload(normalized: dict[str, Any]) -> dict[str, Any]:
    title = normalized.get("title") or "Analysis Report"
    return {
        "title": title,
        "summary": normalized.get("summary", ""),
        "selected_skills": normalized.get("selected_skills", []),
        "caveats": normalized.get("caveats", []),
        "next_checks": normalized.get("next_checks", []),
        "report_md": normalized.get("report_md", f"# {title}\n\nReport generation was limited."),
        "analysis_intent": normalized.get("analysis_intent", {}),
        "candidate_angles": [],
        "chart_specs": [],
        "visual_plan": [],
        "feedback_evaluation": normalized.get("feedback_evaluation", {}),
    }
