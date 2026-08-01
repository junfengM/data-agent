import React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  AlertTriangle,
  BarChart3,
  CheckCircle2,
  Circle,
  FileText,
  ListChecks,
  Table2,
  XCircle,
} from "lucide-react";
import type {
  Artifact,
  CandidateAngle,
  ChartData,
  ChartRow,
  JsonRecord,
  RunResponse,
  TableColumn,
  TableData,
  ValidationResult,
  WorkflowStep,
} from "./types";

// ── Constants ──

export const emptyContextForm = {
  kind: "business_context",
  title: "",
  body: "",
};

export const contextKindLabels: Record<string, string> = {
  business_context: "业务背景",
  metric_definition: "指标定义",
  reporting_preference: "报告偏好",
  known_data_issue: "已知数据问题",
  audience: "受众",
};

export const GATE_LABELS: Record<string, string> = {
  evidence_coverage: "证据覆盖",
  evidence_references: "证据引用",
  source_metadata: "数据源元数据",
  source_metadata_on_evidence: "证据来源元数据",
  schema_compliance: "Schema合规",
  chart_contracts: "图表契约",
  chart_contract_compat: "图表契约兼容",
  context_caveats: "上下文注意事项",
  project_context_coverage: "项目上下文覆盖",
  renderability: "可渲染性",
  chart_encoding: "图表编码",
  source_safety: "数据源安全",
  sensitive_payload: "敏感信息",
  completion_mode: "交付模式",
  preflight: "预检",
};

export const COLORS = ["#6366f1", "#06b6d4", "#f59e0b", "#ef4444", "#10b981", "#8b5cf6", "#ec4899", "#f97316"];

// ── Helper Functions ──

export function asTableData(data: JsonRecord | undefined): TableData | null {
  if (!data || !Array.isArray(data.columns) || !Array.isArray(data.rows)) return null;
  return {
    columns: data.columns.filter(isTableColumn),
    rows: data.rows.filter(isJsonRecord),
  };
}

export function asChartData(data: JsonRecord | undefined): ChartData | null {
  if (!data || !Array.isArray(data.rows)) return null;
  const rows = data.rows.filter(isChartRowFn);
  if (!rows.length) return null;
  return {
    chart_type: typeof data.chart_type === "string" ? data.chart_type : "bar",
    rows,
    source: typeof data.source === "string" ? data.source : undefined,
    unit: typeof data.unit === "string" ? data.unit : undefined,
    description: typeof data.description === "string" ? data.description : undefined,
  };
}

export function isJsonRecord(value: unknown): value is JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isTableColumn(value: unknown): value is TableColumn {
  return isJsonRecord(value) && typeof value.key === "string" && typeof value.label === "string";
}

function isChartRowFn(value: unknown): value is ChartRow {
  return isJsonRecord(value) && typeof value.label === "string" && typeof value.value === "number";
}

export function formatCell(value: unknown): string {
  if (typeof value === "number") return Number.isInteger(value) ? `${value}` : value.toFixed(2);
  if (typeof value === "string") return value;
  if (value === null || value === undefined) return "";
  return JSON.stringify(value);
}

export function artifactTypeLabel(type: string): string {
  const labels: Record<string, string> = {
    markdown_report: "报告产物",
    html_report: "HTML 报告",
    notebook: "Notebook",
    chart: "图表组件",
    dashboard: "仪表盘",
    table: "表格组件",
    run_log: "运行日志",
    structured_report: "结构化报告",
    visual_report: "图文报告",
  };
  return labels[type] ?? type;
}

export function statusLabel(status: string): string {
  const labels: Record<string, string> = {
    pending: "等待中",
    running: "运行中",
    completed: "已完成",
    completed_with_warnings: "已完成（有警告）",
    failed: "失败",
    blocked: "已阻断",
  };
  return labels[status] ?? status;
}

export function statusColorClass(status: string): string {
  if (status === "completed") return "status-ok";
  if (status === "completed_with_warnings") return "status-warn";
  if (status === "failed" || status === "blocked") return "status-err";
  if (status === "running") return "status-info";
  return "";
}

// ── Shared Small Components ──

export function PanelHeader({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <div className="panel-header">
      <h2>{title}</h2>
      <p>{subtitle}</p>
    </div>
  );
}

export function WidgetHeader({ artifact }: { artifact: Artifact }) {
  return (
    <header className="widget-header">
      <div>
        <h2>{artifact.title}</h2>
        <p>{artifactTypeLabel(artifact.type)}</p>
      </div>
      <ArtifactIcon type={artifact.type} />
    </header>
  );
}

export function EmptyState({ text }: { text: string }) {
  return <div className="empty-state">{text}</div>;
}

export function ArtifactIcon({ type }: { type: string }) {
  if (type === "table") return <Table2 size={18} />;
  if (type === "chart" || type === "visual_report") return <BarChart3 size={18} />;
  return <FileText size={18} />;
}

export function MarkdownView({ content }: { content: string }) {
  return (
    <div className="markdown-view">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>
        {content}
      </ReactMarkdown>
    </div>
  );
}

export function ReadinessItem({ ready, text }: { ready: boolean; text: string }) {
  return (
    <div className={`readiness-item ${ready ? "ready" : ""}`}>
      {ready ? <CheckCircle2 size={17} /> : <Circle size={17} />}
      <span>{text}</span>
    </div>
  );
}

// ── Workflow Components ──

export function WorkflowList({ steps }: { steps: WorkflowStep[] }) {
  return (
    <div className="workflow-list">
      {steps.map((step) => {
        const isDone = step.status === "completed" || step.status === "completed_with_warnings";
        const isFailed = step.status === "failed" || step.status === "blocked";
        const colorCls = statusColorClass(step.status);
        return (
          <div className={`workflow-step ${step.status}`} key={step.id}>
            {isDone ? (
              <CheckCircle2 className={colorCls} size={18} />
            ) : isFailed ? (
              <XCircle className={colorCls} size={18} />
            ) : (
              <Circle className={colorCls} size={18} />
            )}
            <div>
              <strong>{step.name}</strong>
              <span>
                {step.skill_id} / {statusLabel(step.status)}
              </span>
              <p>{step.summary}</p>
            </div>
          </div>
        );
      })}
    </div>
  );
}

export function WorkflowView({ run }: { run: RunResponse | null }) {
  if (!run) {
    return (
      <div className="workflow-placeholder">
        <ListChecks size={28} />
        <span>运行后会显示分析、诊断、报告三步状态。</span>
      </div>
    );
  }
  const statusCls = statusColorClass(run.status);
  const warnBadge = run.status === "completed_with_warnings" || run.validation_passed === false;
  return (
    <div className="workflow-view">
      <div className="run-status-bar">
        <span className={`run-status-badge ${statusCls}`}>
          {run.status === "completed_with_warnings" ? (
            <AlertTriangle size={14} />
          ) : (
            <CheckCircle2 size={14} />
          )}
          {statusLabel(run.status)}
        </span>
        {warnBadge && run.validation_passed === false && (
          <span className="validation-warn-badge">
            <AlertTriangle size={14} />
            验证未通过
          </span>
        )}
      </div>
      <WorkflowList steps={run.workflow_steps} />
    </div>
  );
}

// ── Candidate Angle Panel ──

export function CandidateAnglePanel({ angles }: { angles: CandidateAngle[] }) {
  const selected = angles.filter((a) => a.selected);
  const rejected = angles.filter((a) => !a.selected);
  const scoreLabel: Record<string, string> = {
    impact_score: "影响度",
    confidence_score: "置信度",
    actionability_score: "可行动性",
    novelty_score: "新颖性",
    relevance_score: "相关性",
    data_sufficiency_score: "数据充分性",
  };
  return (
    <div className="candidate-angles-panel">
      <h3>
        分析角度 ({selected.length} 已选 / {angles.length} 总计)
      </h3>
      {selected.map((a) => (
        <div className="candidate-angle selected" key={a.id}>
          <span className="angle-badge selected-badge">已选</span>
          <strong>{a.question}</strong>
          {a.linked_evidence_count != null && a.linked_evidence_count > 0 && (
            <span className="angle-evidence-count">{a.linked_evidence_count} 个关联产物</span>
          )}
          <div className="angle-scores">
            {Object.entries(scoreLabel).map(([key, label]) => {
              const score = (a as any)[key] as number;
              return (
                <span key={key} className="score-chip">
                  {label}: {(score * 100).toFixed(0)}%
                </span>
              );
            })}
          </div>
        </div>
      ))}
      {rejected.map((a) => (
        <div className="candidate-angle rejected" key={a.id}>
          <span className="angle-badge rejected-badge">未选</span>
          <strong>{a.question}</strong>
          {a.rejected_reason && <p className="rejected-reason">{a.rejected_reason}</p>}
        </div>
      ))}
    </div>
  );
}

// ── Validation Gate ──

export function ValidationGate({ results, passed }: { results: ValidationResult[]; passed?: boolean }) {
  const sevOrder: Record<string, number> = { fail: 0, warning: 1, pass: 2 };
  const getSev = (r: ValidationResult): string => r.severity || (r.passed ? "pass" : "fail");

  const sorted = [...results].sort((a, b) => {
    const sa = sevOrder[getSev(a)] ?? 0;
    const sb = sevOrder[getSev(b)] ?? 0;
    return sa - sb;
  });

  const passCount = results.filter((r) => getSev(r) === "pass").length;
  const warnCount = results.filter((r) => getSev(r) === "warning").length;
  const failCount = results.filter((r) => getSev(r) === "fail").length;
  const total = results.length;

  const sevIcon = (r: ValidationResult) => {
    const s = getSev(r);
    if (s === "fail") return <XCircle size={14} />;
    if (s === "warning") return <AlertTriangle size={14} />;
    return <CheckCircle2 size={14} />;
  };

  const sevClass = (r: ValidationResult) => `validation-gate-item severity-${getSev(r)}`;

  const severityBadge = (r: ValidationResult) => {
    const s = getSev(r);
    if (s === "fail") return <span className="severity-badge severity-badge-fail">失败</span>;
    if (s === "warning") return <span className="severity-badge severity-badge-warning">警告</span>;
    return <span className="severity-badge severity-badge-pass">通过</span>;
  };

  const gateClass =
    failCount > 0
      ? "validation-gate validation-not-passed"
      : warnCount > 0
        ? "validation-gate validation-warning"
        : "validation-gate validation-passed";

  return (
    <div className={gateClass}>
      <div className="validation-gate-header">
        <span className="validation-summary">
          验证: {passCount}/{total} 通过
          {warnCount > 0 && <span className="validation-warn-count">（{warnCount} 警告）</span>}
        </span>
        {failCount > 0 ? (
          <span className="validation-badge badge-fail">未通过</span>
        ) : warnCount > 0 ? (
          <span className="severity-badge severity-badge-warning">警告</span>
        ) : (
          <span className="validation-badge badge-ok">通过</span>
        )}
      </div>
      {sorted.map((r) => (
        <div className={sevClass(r)} key={r.gate_id}>
          {sevIcon(r)}
          <div>
            <strong>{GATE_LABELS[r.gate_id] || r.gate_id}</strong>
            {r.owner_layer && (
              <span className="owner-layer-badge">{r.owner_layer}</span>
            )}
            <p>{r.message}</p>
            {r.fix_hint && (
              <p className="validation-fix-hint">{r.fix_hint}</p>
            )}
            {r.details && Object.keys(r.details).length > 0 && (
              <pre className="validation-details">{JSON.stringify(r.details, null, 2)}</pre>
            )}
          </div>
          {severityBadge(r)}
        </div>
      ))}
    </div>
  );
}
