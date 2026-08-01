from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import AliasChoices, BaseModel, Field


CANONICAL_CHART_TYPES: list[str] = [
    "line", "area", "stackedArea", "bar", "horizontalBar",
    "stackedBar", "stackedBar100", "horizontalStackedBar", "horizontalStackedBar100",
    "histogram", "scatter", "heatmap", "pie",
    "leaderboard", "sparkline", "funnel", "waterfall", "boxPlot",
]

CHART_INTENTS: list[str] = [
    "comparison", "composition", "decomposition",
    "distribution", "funnel", "lookup",
    "relationship", "status", "trend",
]

INTENT_COMPATIBLE_CHART_TYPES: dict[str, list[str]] = {
    "comparison": ["bar", "horizontalBar", "leaderboard", "scatter"],
    "composition": [
        "horizontalStackedBar", "horizontalStackedBar100",
        "pie", "stackedArea", "stackedBar", "stackedBar100",
    ],
    "decomposition": ["bar", "horizontalBar", "waterfall"],
    "distribution": ["boxPlot", "histogram"],
    "funnel": ["bar", "funnel", "horizontalBar"],
    "lookup": ["leaderboard"],
    "relationship": ["heatmap", "scatter"],
    "status": ["bar", "horizontalBar", "sparkline"],
    "trend": ["area", "bar", "line", "sparkline", "stackedArea"],
}


class ArtifactType(StrEnum):
    markdown_report = "markdown_report"
    html_report = "html_report"
    notebook = "notebook"
    chart = "chart"
    dashboard = "dashboard"
    table = "table"
    run_log = "run_log"
    structured_report = "structured_report"  # debug-only (behind emit_debug_structured_report flag)
    structured_manifest = "structured_manifest"  # deprecated — superseded by visual_report manifest/snapshot
    visual_report = "visual_report"


class RunEventType(StrEnum):
    RUN_STARTED = "run_started"
    CONTEXT_LOADED = "context_loaded"
    DATASET_PROFILE_STARTED = "dataset_profile_started"
    DATASET_PROFILE_COMPLETED = "dataset_profile_completed"
    PREFLIGHT_COMPLETED = "preflight_completed"
    PLANNING_STARTED = "planning_started"
    PLANNING_FAILED = "planning_failed"
    CANDIDATE_ANGLE_INVALID = "candidate_angle_invalid"
    CODE_GENERATED = "code_generated"
    CODE_EXECUTION_STARTED = "code_execution_started"
    CODE_EXECUTION_COMPLETED = "code_execution_completed"
    DIAGNOSIS_COMPLETED = "diagnosis_completed"
    REPORT_GENERATION_STARTED = "report_generation_started"
    REPORT_GENERATED = "report_generated"
    VALIDATION_STARTED = "validation_started"
    VALIDATION_COMPLETED = "validation_completed"
    PLANNER_FINALIZED = "planner_finalized"
    PLANNER_PAYLOAD_INVALID = "planner_payload_invalid"
    RUN_MODE_PREFLIGHT_ONLY = "run_mode_preflight_only"


class HealthResponse(BaseModel):
    status: str


class SkillSummary(BaseModel):
    id: str
    name: str
    path: Path
    trigger: str = ""


class ModelConfigSummary(BaseModel):
    id: str
    provider: str
    base_url: str | None = None
    api_key_env: str
    model: str
    temperature: float | None = None
    max_tokens: int | None = None
    api_key_configured: bool = False


class DatasetRecord(BaseModel):
    id: str
    filename: str
    path: Path
    content_type: str | None = None
    created_at: str | None = None
    project_id: str | None = None


class AnalysisProject(BaseModel):
    id: str
    name: str
    description: str = ""
    status: str = "active"
    created_at: str | None = None
    updated_at: str | None = None


class AnalysisProjectCreate(BaseModel):
    name: str
    description: str = ""


class AnalysisProjectUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    status: str | None = None


class ProjectContext(BaseModel):
    id: str
    project_id: str
    kind: str
    title: str
    body: str
    created_at: str | None = None
    updated_at: str | None = None


class ProjectContextCreate(BaseModel):
    kind: str = "business_context"
    title: str
    body: str


class ProjectContextUpdate(BaseModel):
    kind: str | None = None
    title: str | None = None
    body: str | None = None


class ColumnProfile(BaseModel):
    name: str
    dtype: str
    non_null_count: int
    null_count: int
    null_pct: float
    unique_count: int
    sample_values: list[str] = Field(default_factory=list)
    min_value: str | None = None
    max_value: str | None = None
    mean_value: float | None = None


class DatasetProfile(BaseModel):
    dataset_id: str
    filename: str
    row_count: int
    column_count: int
    columns: list[ColumnProfile]
    warnings: list[str] = Field(default_factory=list)


class AnalysisRequest(BaseModel):
    question: str
    project_id: str | None = None
    dataset_ids: list[str] = Field(default_factory=list)
    model_config_id: str | None = None
    skill_id: str | None = None
    context: str | None = None
    run_mode: Literal["full", "preflight_only", "plan_only"] = "full"


class Artifact(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    type: ArtifactType
    title: str
    path: Path | None = None
    content: str | None = None
    data: dict[str, Any] | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ReportBlockType(StrEnum):
    heading = "heading"
    prose = "prose"
    table = "table"
    chart = "chart"
    callout = "callout"
    source_note = "source_note"
    dashboard = "dashboard"
    notebook = "notebook"


class ReportBlock(BaseModel):
    """A single block in a structured report."""
    type: ReportBlockType
    data: dict[str, Any] = Field(default_factory=dict)


class ToolCall(BaseModel):
    name: str
    input_summary: str
    output_summary: str | None = None
    status: str = "pending"


# ── Artifact Manifest + Snapshot models (Codex Data Analytics plugin contract) ──


class ArtifactBlockType(StrEnum):
    markdown = "markdown"
    metric_strip = "metric-strip"
    chart = "chart"
    table = "table"
    kpi_grid = "kpi_grid"
    delta_bridge = "delta_bridge"
    leaderboard_pair = "leaderboard_pair"
    trend_panel = "trend_panel"
    composition_panel = "composition_panel"
    insight_banner = "insight_banner"
    risk_panel = "risk_panel"
    next_action_list = "next_action_list"
    page_summary = "page_summary"
    decision_matrix = "decision_matrix"
    data_quality_panel = "data_quality_panel"
    forecast_band = "forecast_band"
    metric_change = "metric_change"
    stage_timeline = "stage_timeline"
    comparison_grid = "comparison_grid"
    executive_storyboard = "executive_storyboard"
    adaptive_story = "adaptive_story"


class ReportIntent(BaseModel):
    audience: str = "analyst"
    format: str = "deep_dive"
    depth: str = "standard"
    visual_density: str = "medium"
    confidence: str = "medium"
    rationale: list[str] = Field(default_factory=list)


class ReportClaim(BaseModel):
    id: str = Field(default_factory=lambda: f"claim_{uuid4().hex[:8]}")
    text: str
    evidence_ids: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    confidence: str = "medium"
    caveats: list[str] = Field(default_factory=list)
    claim_type: str = "fact"
    impact: str = "medium"
    time_horizon: str = "now"
    metric_refs: list[str] = Field(default_factory=list)
    supporting_action_ids: list[str] = Field(default_factory=list)


class ActionItem(BaseModel):
    id: str = Field(default_factory=lambda: f"action_{uuid4().hex[:8]}")
    text: str
    priority: str = "medium"
    owner_hint: str | None = None
    expected_impact: str | None = None
    effort: str | None = None
    due_hint: str | None = None
    supporting_claim_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


class ReportSection(BaseModel):
    id: str
    role: str
    title: str
    claim_ids: list[str] = Field(default_factory=list)
    action_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    preferred_blocks: list[str] = Field(default_factory=list)
    evidence_budget: int | None = None


class ReportPlan(BaseModel):
    audience: str = "analyst"
    format: str = "deep_dive"
    depth: str = "standard"
    visual_density: str = "medium"
    sections: list[ReportSection] = Field(default_factory=list)
    evidence_budget: dict[str, int] = Field(default_factory=dict)
    renderer_notes: list[str] = Field(default_factory=list)


class VisualPlanItem(BaseModel):
    id: str = Field(default_factory=lambda: f"visual_{uuid4().hex[:8]}")
    block_type: str
    source_section: str | None = None
    source_ref: str | None = None
    title: str | None = None
    intent: str | None = None
    priority: str = "primary"
    options: dict[str, Any] = Field(default_factory=dict)


# ── Two-layer visual report architecture constants ──

RENDERER_TARGET_MD_VISUAL = "md_visual"
RENDERER_TARGET_EVIDENCE_COMPONENT = "evidence_component"
RENDERER_TARGET_APPENDIX = "appendix"
RENDERER_TARGET_NARRATIVE = "narrative"

RENDERER_TARGETS = frozenset({
    RENDERER_TARGET_MD_VISUAL,
    RENDERER_TARGET_EVIDENCE_COMPONENT,
    RENDERER_TARGET_APPENDIX,
    RENDERER_TARGET_NARRATIVE,
})

BLOCK_ORIGIN_VISUAL_DECK = "visual_deck"
BLOCK_ORIGIN_ARTIFACT_MANIFEST = "artifact_manifest"
BLOCK_ORIGIN_VISUAL_REPORT_PLANNER = "visual_report_planner"
BLOCK_ORIGIN_REPORT_PLAN = "report_plan"
BLOCK_ORIGIN_READING_FLOW = "reading_flow"

BLOCK_ORIGINS = frozenset({
    BLOCK_ORIGIN_VISUAL_DECK,
    BLOCK_ORIGIN_ARTIFACT_MANIFEST,
    BLOCK_ORIGIN_VISUAL_REPORT_PLANNER,
    BLOCK_ORIGIN_REPORT_PLAN,
    BLOCK_ORIGIN_READING_FLOW,
})


class EvidenceLink(BaseModel):
    evidence_id: str
    method: str = "text_similarity"
    score: float | None = None
    matched_terms: list[str] = Field(default_factory=list)
    reason: str | None = None


class ArtifactBlock(BaseModel):
    """A block in the manifest reading order.

    The base Codex-style blocks reference charts/tables/cards by id. The
    visual-report blocks carry small inline item arrays so the renderer can
    create management-ready pages without forcing every component through a
    dense table first.
    """
    id: str
    type: ArtifactBlockType
    body: str | None = None
    title: str | None = None
    subtitle: str | None = None
    text: str | None = None
    summary: str | None = None
    note: str | None = None
    dataset: str | None = None
    items: list[dict[str, Any]] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    positive: list[dict[str, Any]] = Field(default_factory=list)
    negative: list[dict[str, Any]] = Field(default_factory=list)
    left_title: str | None = None
    right_title: str | None = None
    card_ids: list[str] = Field(default_factory=list)
    chart_id: str | None = None
    table_id: str | None = None
    source_id: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    evidence_links: list[EvidenceLink] = Field(default_factory=list)
    linked_angle_ids: list[str] = Field(default_factory=list)
    claim_ids: list[str] = Field(default_factory=list)
    action_ids: list[str] = Field(default_factory=list)
    evidence_priority: str = "secondary"
    report_intent: ReportIntent | None = None
    section_role: str | None = None
    source_section: str | None = None
    source_excerpt: str | None = None
    visual_plan_id: str | None = None
    visual_intent: str | None = None
    variant: str | None = None
    display_mode: str | None = None
    coverage_id: str | None = None
    renderer_target: str | None = None  # see RENDERER_TARGETS above
    block_origin: str | None = None  # see BLOCK_ORIGINS above


class ChartEncoding(BaseModel):
    field: str | None = None
    fields: list[str] | None = None
    type: str | None = None
    aggregate: str | None = None
    format: str | None = None
    label: str | None = None
    unit: str | None = None


class ChartEncodings(BaseModel):
    x: ChartEncoding | None = None
    y: ChartEncoding | None = None
    color: ChartEncoding | None = None
    size: ChartEncoding | None = None
    facet: ChartEncoding | None = None
    label: ChartEncoding | None = None


class ManifestChart(BaseModel):
    id: str
    title: str
    subtitle: str | None = None
    type: str
    dataset: str
    encodings: ChartEncodings = Field(default_factory=ChartEncodings)
    intent: str | None = None
    compatible_types: list[str] = Field(default_factory=list)
    source_id: str | None = None
    description: str | None = None
    unit: str | None = None
    x_axis_title: str | None = None
    y_axis_title: str | None = None
    value_format: str | None = None
    render_mode: str = "vega"
    asset_path: str | None = None
    linked_angle_ids: list[str] = Field(default_factory=list)


class TableColumn(BaseModel):
    field: str
    label: str
    format: str | None = None
    type: str | None = None
    unit: str | None = None
    align: str | None = None


class ManifestTable(BaseModel):
    id: str
    title: str
    subtitle: str | None = None
    dataset: str
    columns: list[TableColumn] = Field(default_factory=list)
    source_id: str | None = None
    density: str | None = None
    linked_angle_ids: list[str] = Field(default_factory=list)
    evidence_priority: str = "secondary"


class CardMetric(BaseModel):
    label: str
    field: str
    format: str | None = None
    signed: bool | None = None
    comparison_field: str | None = None
    delta_field: str | None = None
    status_field: str | None = None
    caveat: str | None = None


class ManifestCard(BaseModel):
    id: str
    dataset: str
    description: str | None = None
    metrics: list[CardMetric] = Field(default_factory=list)
    evidence_priority: str = "primary"


class SourceQuery(BaseModel):
    engine: str | None = None
    sql: str | None = None
    description: str | None = None
    tables_used: list[str] = Field(default_factory=list)
    filters: list[str] = Field(default_factory=list)
    metric_definitions: list[str] = Field(default_factory=list)
    executed_at: str | None = None


class ManifestSource(BaseModel):
    id: str
    label: str | None = None
    path: str | None = None
    href: str | None = None
    query: SourceQuery | None = None
    step_id: str | None = None


class EvidenceEntry(BaseModel):
    """A single evidence item in the evidence map with source provenance."""
    id: str
    type: str
    title: str
    source_dataset: str | None = None
    step_id: str | None = None
    row_count: int | None = None
    caveats: list[str] = Field(default_factory=list)
    linked_angle_ids: list[str] = Field(default_factory=list)
    priority: str = "secondary"


class CandidateAngle(BaseModel):
    """An analysis angle with scoring metadata. Persisted in run log for decision traceability."""
    id: str = Field(default_factory=lambda: uuid4().hex[:8])
    question: str = Field(validation_alias=AliasChoices("question", "angle", "title", "name"))
    dimensions: list[str] = Field(default_factory=list)
    measures: list[str] = Field(default_factory=list)
    expected_evidence: str = ""
    impact_score: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence_score: float = Field(default=0.0, ge=0.0, le=1.0)
    actionability_score: float = Field(default=0.0, ge=0.0, le=1.0)
    novelty_score: float = Field(default=0.0, ge=0.0, le=1.0)
    relevance_score: float = Field(default=0.0, ge=0.0, le=1.0)
    data_sufficiency_score: float = Field(default=0.0, ge=0.0, le=1.0)
    selected: bool = False
    rejected_reason: str | None = None

    @property
    def composite_score(self) -> float:
        """Weighted composite: impact(0.25) + confidence(0.2) + actionability(0.2)
        + relevance(0.2) + data_sufficiency(0.15). Novelty excluded from ranking."""
        return (
            self.impact_score * 0.25
            + self.confidence_score * 0.20
            + self.actionability_score * 0.20
            + self.relevance_score * 0.20
            + self.data_sufficiency_score * 0.15
        )


# Boundary rules for candidate angle selection
MAX_CANDIDATE_ANGLES = 7
MAX_SELECTED_ANGLES = 5
MIN_DATA_SUFFICIENCY = 0.15
MIN_ANGLE_SCORE = 0.2


class ArtifactManifest(BaseModel):
    version: int = 1
    surface: str = "report"
    title: str
    description: str | None = None
    generated_at: str | None = None
    report_intent: ReportIntent | None = None
    report_plan: ReportPlan | None = None
    claims: list[ReportClaim] = Field(default_factory=list)
    actions: list[ActionItem] = Field(default_factory=list)
    blocks: list[ArtifactBlock] = Field(default_factory=list)
    charts: list[ManifestChart] = Field(default_factory=list)
    tables: list[ManifestTable] = Field(default_factory=list)
    cards: list[ManifestCard] = Field(default_factory=list)
    sources: list[ManifestSource] = Field(default_factory=list)
    filters: list[dict[str, Any]] = Field(default_factory=list)
    candidate_angles: list[CandidateAngle] = Field(default_factory=list)
    chart_specs: list[dict[str, Any]] = Field(default_factory=list)
    visual_plan: list[VisualPlanItem] = Field(default_factory=list)
    visual_coverage: list[dict[str, Any]] = Field(default_factory=list)
    visual_iteration: list[dict[str, Any]] = Field(default_factory=list)
    visual_recipes: list[dict[str, Any]] = Field(default_factory=list)
    semantic_layer: dict[str, Any] | None = None


class ArtifactSnapshot(BaseModel):
    version: int = 1
    status: str = "ready"
    generated_at: str | None = None
    datasets: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    access_issues: list[dict[str, Any]] = Field(default_factory=list)
    evidence_map: list[EvidenceEntry] = Field(default_factory=list)


class ArtifactPackage(BaseModel):
    """Exportable artifact package: manifest + snapshot + metadata."""
    package_version: int = 1
    id: str = Field(default_factory=lambda: uuid4().hex)
    title: str
    generated_at: str
    project_id: str | None = None
    question: str | None = None
    manifest: ArtifactManifest
    snapshot: ArtifactSnapshot
    metadata: dict[str, Any] = Field(default_factory=dict)


class VisualReportData(BaseModel):
    """Container for manifest + snapshot pair used as visual_report artifact data."""
    manifest: ArtifactManifest
    snapshot: ArtifactSnapshot


class WorkflowStep(BaseModel):
    id: str
    name: str
    skill_id: str
    status: str = "pending"
    summary: str = ""


class ValidationResultModel(BaseModel):
    gate_id: str
    passed: bool
    message: str
    severity: str
    details: dict[str, Any] = Field(default_factory=dict)
    fix_hint: str | None = None
    owner_layer: str | None = None
    related_block_ids: list[str] = Field(default_factory=list)
    related_evidence_ids: list[str] = Field(default_factory=list)
    can_auto_repair: bool = False


class RunResponse(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    status: str
    skill_id: str
    question: str
    project_id: str | None = None
    run_mode: str = "full"
    artifacts: list[Artifact] = Field(default_factory=list)
    tool_calls: list[ToolCall] = Field(default_factory=list)
    workflow_steps: list[WorkflowStep] = Field(default_factory=list)
    validation_results: list[ValidationResultModel] = Field(default_factory=list)
    validation_passed: bool | None = None


class SemanticLayerCreate(BaseModel):
    name: str
    path: str


class SemanticLayerResponse(BaseModel):
    id: str
    project_id: str | None = None
    name: str
    path: str
    created_at: str | None = None


# ── Typed semantic-layer definition models ──


class MetricDefinition(BaseModel):
    """Canonical metric definition in a project semantic layer."""
    id: str = Field(default_factory=lambda: uuid4().hex[:8])
    name: str
    description: str = ""
    formula: str = ""
    aggregation: str = ""
    grain: str = ""
    unit: str = ""
    dimensions: list[str] = Field(default_factory=list)
    filters: list[str] = Field(default_factory=list)
    sources: list[dict[str, str]] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)
    owner: str = ""


class DimensionDefinition(BaseModel):
    """Canonical dimension definition."""
    id: str = Field(default_factory=lambda: uuid4().hex[:8])
    name: str
    type: str = "string"
    grain: list[str] = Field(default_factory=list)
    source_column: str = ""
    source_table: str = ""
    values: list[str] = Field(default_factory=list)
    description: str = ""


class SourceDefinition(BaseModel):
    """Canonical source table/file definition."""
    id: str = Field(default_factory=lambda: uuid4().hex[:8])
    name: str
    type: str = "table"
    path: str = ""
    grain: str = ""
    primary_key: str = ""
    columns: list[dict[str, str]] = Field(default_factory=list)
    update_frequency: str = ""
    caveats: list[str] = Field(default_factory=list)


class OnboardingUpdate(BaseModel):
    step: str
    completed_steps: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SourceRoutingUpdate(BaseModel):
    category: str
    preference: str
