export type ModuleId = "projects" | "data" | "context" | "semantic-layer" | "run" | "artifacts" | "trace";

export type JsonRecord = Record<string, unknown>;

export type Skill = {
  id: string;
  name: string;
  trigger: string;
  path: string;
};

export type Artifact = {
  id: string;
  type: string;
  title: string;
  content?: string;
  path?: string;
  data?: JsonRecord;
};

export type Dataset = {
  id: string;
  filename: string;
  path: string;
  content_type?: string;
  created_at?: string;
  project_id?: string;
};

export type ModelConfig = {
  id: string;
  provider: string;
  base_url?: string | null;
  api_key_env: string;
  model: string;
  temperature?: number | null;
  max_tokens?: number | null;
  api_key_configured: boolean;
};

export type AnalysisProject = {
  id: string;
  name: string;
  description: string;
  status: string;
  created_at?: string;
  updated_at?: string;
};

export type ProjectContext = {
  id: string;
  project_id: string;
  kind: string;
  title: string;
  body: string;
  created_at?: string;
  updated_at?: string;
};

export type WorkflowStep = {
  id: string;
  name: string;
  skill_id: string;
  status: string;
  summary: string;
};

export type ToolCall = {
  name: string;
  input_summary: string;
  output_summary?: string;
  status: string;
};

export type ValidationResult = {
  gate_id: string;
  passed: boolean;
  message: string;
  severity: "pass" | "warning" | "fail";
  details?: Record<string, any>;
  fix_hint?: string | null;
  owner_layer?: string | null;
  related_block_ids?: string[];
  related_evidence_ids?: string[];
  can_auto_repair?: boolean;
};

export type RunMode = "full" | "preflight_only" | "plan_only";

export type RunResponse = {
  id: string;
  status: string;
  skill_id: string;
  project_id?: string;
  question: string;
  run_mode?: string;
  artifacts: Artifact[];
  tool_calls: ToolCall[];
  workflow_steps: WorkflowStep[];
  validation_results?: ValidationResult[];
  validation_passed?: boolean;
};

export type RunSummary = {
  id: string;
  status: string;
  skill_id?: string;
  question: string;
  project_id?: string;
  artifact_count: number;
  tool_call_count: number;
  workflow_step_count: number;
  has_visual_report?: boolean;
  has_run_log?: boolean;
};

export type CandidateAngle = {
  id: string;
  question: string;
  dimensions: string[];
  measures: string[];
  expected_evidence: string;
  impact_score: number;
  confidence_score: number;
  actionability_score: number;
  novelty_score: number;
  relevance_score: number;
  data_sufficiency_score: number;
  selected: boolean;
  rejected_reason?: string;
  linked_evidence_count?: number;
};

export type TableColumn = {
  key: string;
  label: string;
};

export type TableData = {
  columns: TableColumn[];
  rows: JsonRecord[];
};

export type ChartRow = {
  label: string;
  value: number;
  secondary_value?: number;
  x_value?: number;
  color?: unknown;
  min?: number;
  q1?: number;
  q3?: number;
  max?: number;
};

export type ChartData = {
  chart_type: string;
  rows: ChartRow[];
  source?: string;
  unit?: string;
  description?: string;
  x_axis_title?: string;
  y_axis_title?: string;
};

export type SemanticLayerMeta = {
  id?: string;
  name?: string;
  path?: string;
  metrics?: Array<{ name: string; formula: string; grain: string; caveat?: string }>;
  dimensions?: Array<{ name: string; source_column: string; source_table: string }>;
};

/** Mirrors server/app/models/schemas.py RENDERER_TARGETS. */
export type RendererTarget = "md_visual" | "evidence_component" | "appendix" | "narrative";

/** Mirrors server/app/models/schemas.py BLOCK_ORIGINS. */
export type BlockOrigin = "visual_deck" | "artifact_manifest" | "visual_report_planner" | "report_plan" | "reading_flow";

/** A single block within a visual report manifest.
 *  All fields are optional because existing runs may not have them;
 *  type-narrow with truthiness checks. */
export type ManifestBlock = {
  id?: string;
  type?: string;
  /** Which renderer surface this block belongs to. */
  renderer_target?: RendererTarget;
  /** Which backend module created this block. */
  block_origin?: BlockOrigin;
  /** Real evidence ids (chart_id / table_id / card_ids) for evidence_component blocks. */
  evidence_ids?: string[];
  /** Chart asset id for chart-type evidence_component blocks. */
  chart_id?: string;
  /** Table asset id for table-type evidence_component blocks. */
  table_id?: string;
  /** Card ids for metric-strip evidence_component blocks. */
  card_ids?: string[];
  /** Source section anchor for md_visual blocks. */
  source_section?: string;
  /** Markdown body for prose/narrative blocks. */
  body?: string;
  /** Source details display_mode for visualized markdown. */
  display_mode?: string;
  title?: string;
  [key: string]: unknown;
};
