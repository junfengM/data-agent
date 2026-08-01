import React from "react";
import {
  Archive,
  BarChart3,
  ChevronDown,
  Download,
  ExternalLink,
  FileCode,
  Image,
  Link2,
  ListChecks,
  PanelLeftClose,
  PanelLeftOpen,
  Table2,
} from "lucide-react";
import { toBlob } from "html-to-image";
import type {
  Artifact,
  CandidateAngle,
  JsonRecord,
  RendererTarget,
  RunResponse,
  RunSummary,
  ValidationResult,
  WorkflowStep,
  ToolCall,
} from "../types";
import { apiFetch, resolveApiUrl } from "../apiClient";
import { fetchRuns } from "../api/runs";
import { buildChartData, buildHeatmapRawData } from "../utils/chartAdapters";
import { humanizeReportLabel, prepareReportBlocks } from "../utils/reportLayout";
import { COLORS, RechartsRenderer } from "./RechartsRenderer";
import {
  ArtifactIcon,
  artifactTypeLabel,
  asChartData,
  asTableData,
  CandidateAnglePanel,
  EmptyState,
  formatCell,
  MarkdownView,
  PanelHeader,
  ValidationGate,
  WidgetHeader,
  WorkflowList,
} from "../shared";
import { ArtifactEvidenceDetails } from "./ArtifactEvidenceDetails";
import {
  VisualAdaptiveStory,
  VisualComparisonGrid,
  VisualCompositionPanel,
  VisualDataQualityPanel,
  VisualDecisionMatrix,
  VisualDeltaBridge,
  VisualExecutiveStoryboard,
  VisualForecastBand,
  VisualInsightBanner,
  VisualKpiGrid,
  VisualLeaderboardPair,
  VisualMetricChange,
  VisualNextActionList,
  VisualPageSummary,
  VisualRiskPanel,
  VisualStageTimeline,
  VisualTrendPanel,
} from "./VisualReportBlocks";
import "./artifact-layout.css";

type ArtifactsProps = {
  activeArtifact?: Artifact;
  activeArtifactId: string;
  onOpenRun: (runId: string) => void;
  run: RunResponse | null;
  selectedProjectId: string;
  setActiveArtifactId: React.Dispatch<React.SetStateAction<string>>;
};

export default function ArtifactModule(props: ArtifactsProps) {
  const [isRailCollapsed, setIsRailCollapsed] = React.useState(false);
  const [historyRuns, setHistoryRuns] = React.useState<RunSummary[]>([]);
  const [isLoadingHistory, setIsLoadingHistory] = React.useState(false);
  const artifacts = sortArtifactsForReportReading(props.run?.artifacts ?? []);
  const visualArtifact = pickVisualReportArtifact(artifacts);
  const displayArtifact = props.activeArtifact ?? visualArtifact;
  const displayArtifactId = displayArtifact?.id ?? props.activeArtifactId;

  React.useEffect(() => {
    let cancelled = false;
    setIsLoadingHistory(true);
    fetchRuns(props.selectedProjectId || undefined)
      .then((runs) => {
        if (!cancelled) setHistoryRuns(runs);
      })
      .catch(() => {
        if (!cancelled) setHistoryRuns([]);
      })
      .finally(() => {
        if (!cancelled) setIsLoadingHistory(false);
      });
    return () => {
      cancelled = true;
    };
  }, [props.selectedProjectId, props.run?.id]);

  return (
    <div className={`artifact-layout ${isRailCollapsed ? "rail-collapsed" : ""}`}>
      <aside className="artifact-rail">
        <div className="artifact-rail-header">
          <PanelHeader title="产物列表" subtitle={props.run ? `Run ${props.run.id.slice(0, 8)}` : "暂无运行"} />
          <button aria-label="收起产物列表" className="artifact-rail-toggle" onClick={() => setIsRailCollapsed(true)} title="收起产物列表" type="button">
            <PanelLeftClose size={16} />
          </button>
        </div>
        <section className="artifact-history">
          <div className="artifact-history-heading">
            <strong>历史报告</strong>
            <span>{isLoadingHistory ? "加载中" : `${historyRuns.length} 次运行`}</span>
          </div>
          {historyRuns.length ? (
            <div className="artifact-history-list">
              {historyRuns.map((run) => (
                <button
                  className={`artifact-history-item ${props.run?.id === run.id ? "selected" : ""}`}
                  key={run.id}
                  onClick={() => props.onOpenRun(run.id)}
                  type="button"
                >
                  <span>{run.question}</span>
                  <small>Run {run.id.slice(0, 8)} · {run.status} · {run.artifact_count} 个产物</small>
                </button>
              ))}
            </div>
          ) : (
            <EmptyState text="暂无历史报告。" />
          )}
        </section>
        {artifacts.length ? (
          <div className="artifact-list" role="list">
            {artifacts.map((artifact) => (
              <button className={`artifact-item ${displayArtifactId === artifact.id ? "selected" : ""}`} key={artifact.id} onClick={() => props.setActiveArtifactId(artifact.id)} type="button">
                <ArtifactIcon type={artifact.type} />
                <span>{artifact.title}</span>
                <small>{artifactTypeLabel(artifact.type)}</small>
              </button>
            ))}
          </div>
        ) : <EmptyState text="还没有产物。请先运行一次工作流。" />}
      </aside>
      <section className="artifact-stage">
        {isRailCollapsed && <button className="artifact-rail-reopen" onClick={() => setIsRailCollapsed(false)} type="button"><PanelLeftOpen size={16} /> 产物列表</button>}
        {displayArtifact ? <ArtifactWidget artifact={displayArtifact} runId={props.run?.id} /> : <EmptyState text="请选择一个产物。" />}
      </section>
    </div>
  );
}

export function ArtifactWidget({ artifact, runId }: { artifact: Artifact; runId?: string }) {
  if (artifact.type === "table") return <TableWidget artifact={artifact} />;
  if (artifact.type === "chart") return <ChartWidget artifact={artifact} runId={runId} />;
  if (artifact.type === "run_log") return <RunLogWidget artifact={artifact} />;
  if (artifact.type === "markdown_report") return <ReportWidget artifact={artifact} />;
  if (artifact.type === "html_report" || artifact.type === "notebook") return <FileArtifactWidget artifact={artifact} runId={runId} />;
  if (artifact.type === "structured_report") return <StructuredReportWidget artifact={artifact} runId={runId} />;
  if (artifact.type === "visual_report") return <ManifestReportWidget artifact={artifact} runId={runId} />;
  return <ReportWidget artifact={artifact} />;
}

export function ReportWidget({ artifact }: { artifact: Artifact }) {
  return <article className="artifact-widget report-widget"><WidgetHeader artifact={artifact} /><MarkdownView content={artifact.content || "暂无报告内容。"} /></article>;
}

export function StructuredReportWidget({ artifact, runId }: { artifact: Artifact; runId?: string }) {
  const blocks = Array.isArray(artifact.data?.blocks) ? (artifact.data.blocks as Array<{ type: string; data: Record<string, unknown> }>) : [];
  return (
    <article className="artifact-widget structured-report-widget">
      <WidgetHeader artifact={artifact} />
      <div className="structured-report-blocks">
        {blocks.length ? blocks.map((block, i) => <ReportBlock key={i} block={block} runId={runId} />) : <EmptyState text="暂无结构化报告内容。" />}
      </div>
    </article>
  );
}

function ReportBlock({ block, runId }: { block: { type: string; data: Record<string, unknown> }; runId?: string }) {
  const d = block.data || {};
  switch (block.type) {
    case "heading": {
      const level = typeof d.level === "number" ? d.level : 2;
      const Tag = `h${Math.min(Math.max(level, 1), 6)}` as keyof JSX.IntrinsicElements;
      return <Tag className="report-heading">{String(d.text ?? "")}</Tag>;
    }
    case "prose": return <MarkdownView content={String(d.markdown ?? "")} />;
    case "table": return <InlineTable title={String(d.title ?? "")} columns={toColumnList(d.columns)} rows={toRecordList(d.rows)} />;
    case "chart": return <div className="report-chart">{d.title ? <h4 className="report-chart-title">{String(d.title)}</h4> : null}{d.render_mode === "file" ? <FileChartPreview path={String(d.path ?? "")} runId={runId} title={String(d.title ?? "图表")} /> : <p className="chart-file-hint">图表类型: {String(d.chart_type ?? "unknown")}</p>}</div>;
    case "metric_card": return <div className="report-metric-card"><span className="metric-label">{String(d.label ?? "")}</span><span className="metric-value">{String(d.value ?? "")}</span>{d.delta ? <span className="metric-delta">{String(d.delta)}</span> : null}</div>;
    case "callout": return <div className={`report-callout callout-${String(d.severity ?? "info")}`}>{String(d.text ?? "")}</div>;
    case "source_note": return <small className="report-source-note">{String(d.text ?? "")}</small>;
    default: return <pre className="report-unknown-block">{JSON.stringify(block, null, 2)}</pre>;
  }
}

type ReportViewMode = "reading" | "evidence" | "audit";

export function ManifestReportWidget({ artifact, runId }: { artifact: Artifact; runId?: string }) {
  const exportSurfaceRef = React.useRef<HTMLElement | null>(null);
  const [viewMode, setViewMode] = React.useState<ReportViewMode>("reading");
  const rawManifest = artifact.data?.manifest as Record<string, unknown> | undefined;
  const rawSnapshot = artifact.data?.snapshot as Record<string, unknown> | undefined;
  if (!rawManifest || !rawSnapshot) return <pre>Invalid manifest artifact</pre>;

  const visualReport = buildVisualReportModel(rawManifest, rawSnapshot);
  const { manifest, charts, tables, cards, datasets, sources, evidenceMap } = visualReport;
  const manifestTitle = String(manifest.title || artifact.title || "报告");
  const allBlocks = prepareReportBlocks(visualReport.blocks, manifestTitle);
  const blocks = filterBlocksByMode(allBlocks, viewMode);
  const validationResults = Array.isArray(artifact.data?.validation_results) ? (artifact.data.validation_results as ValidationResult[]) : [];
  const validationPassed = artifact.data?.validation_passed as boolean | undefined;
  const prominentValidationResults = validationResults.filter((result) => result.severity === "fail" || (!result.passed && result.severity !== "pass"));
  const failCount = validationResults.filter((r) => r.severity === "fail" || !r.passed).length;
  const warnCount = validationResults.filter((r) => r.severity === "warning").length;
  const passCount = validationResults.filter((r) => r.passed && r.severity !== "fail").length;

  async function handleDownloadPackage() {
    if (!runId) return;
    const response = await apiFetch(`/api/runs/${runId}/export`);
    if (!response.ok) return alert("导出失败");
    downloadBlob(await response.blob(), `artifact-package-${runId.slice(0, 8)}.json`);
  }

  function handleDownloadHtml() {
    const node = exportSurfaceRef.current;
    if (!node) return;
    downloadBlob(new Blob([createStandaloneHtml(node, manifestTitle)], { type: "text/html;charset=utf-8" }), `${safeFilename(manifestTitle)}.html`);
  }

  async function handleDownloadImage() {
    const node = exportSurfaceRef.current;
    if (!node) return;
    try {
      const blob = await toBlob(node, { backgroundColor: "#ffffff", cacheBust: true, pixelRatio: 2 });
      if (!blob) throw new Error("浏览器没有生成图片文件。");
      downloadBlob(blob, `${safeFilename(manifestTitle)}.png`);
    } catch (error) {
      alert(error instanceof Error ? error.message : "导出图片失败");
    }
  }

  return (
    <article className="artifact-widget structured-report-widget manifest-report-widget">
      <div className="report-actionbar">
        <div className="report-mode-toggles">
          <button className={`mode-toggle ${viewMode === "reading" ? "active" : ""}`} onClick={() => setViewMode("reading")} type="button" title="阅读模式：叙述 + 可视化 + 关键图表">阅读</button>
          <button className={`mode-toggle ${viewMode === "evidence" ? "active" : ""}`} onClick={() => setViewMode("evidence")} type="button" title="证据模式：仅图表、表格、指标条">证据</button>
          <button className={`mode-toggle ${viewMode === "audit" ? "active" : ""}`} onClick={() => setViewMode("audit")} type="button" title="审计模式：所有块 + 元数据">审计</button>
        </div>
        <details className="report-export-menu">
          <summary className="ghost-button export-button"><Download size={16} /> 导出 <ChevronDown size={14} /></summary>
          <div className="report-export-menu-list">
            <button onClick={handleDownloadImage} type="button"><Image size={16} /> 导出为图片</button>
            <button onClick={handleDownloadHtml} type="button"><FileCode size={16} /> 导出为网页</button>
            {runId && <button onClick={handleDownloadPackage} type="button"><Archive size={16} /> 导出包</button>}
          </div>
        </details>
      </div>
      <section className="artifact-export-surface" ref={exportSurfaceRef}>
        <header className="manifest-report-header">
          <span className="manifest-kicker">图文报告</span>
          <h2 className="manifest-title">{manifestTitle}</h2>
          <p className="manifest-subtitle">
            {String(manifest.description || `${charts.length} 个图表 · ${tables.length} 个表格 · ${sources.length} 个数据来源`)}
          </p>
          {validationResults.length > 0 && (
            <div className={`manifest-validation-badge ${failCount > 0 ? "has-fails" : warnCount > 0 ? "has-warnings" : "all-pass"}`}>
              <ListChecks size={14} />
              <span>验证：{passCount}/{validationResults.length} 通过{failCount > 0 ? ` · ${failCount} 失败` : ""}{warnCount > 0 ? ` · ${warnCount} 警告` : ""}</span>
            </div>
          )}
        </header>
        {prominentValidationResults.length > 0 ? <ValidationAlert results={prominentValidationResults} /> : null}
        <div className="structured-report-blocks">
          {blocks.length ? blocks.map((block, i) => <ManifestBlock key={i} block={block} charts={charts} tables={tables} cards={cards} datasets={datasets} sources={sources} evidenceMap={evidenceMap} runId={runId} viewMode={viewMode} />) : <EmptyState text="暂无图文报告内容。" />}
        </div>
        {validationResults.length > 0 && <details className="manifest-validation-section"><summary className="manifest-validation-summary"><ListChecks size={16} /> 校验结果 ({validationResults.filter((r) => r.passed).length}/{validationResults.length} 通过)</summary><ValidationGate results={validationResults} passed={validationPassed} /></details>}
        {(sources.length > 0 || evidenceMap.length > 0) && <ManifestFooter sources={sources} evidenceMap={evidenceMap} />}
      </section>
    </article>
  );
}

function ValidationAlert({ results }: { results: ValidationResult[] }) {
  return (
    <section className="report-callout callout-warning">
      <strong>报告校验提示</strong>
      <ul>
        {results.slice(0, 4).map((result) => <li key={result.gate_id}>{result.message}</li>)}
      </ul>
    </section>
  );
}

function ManifestBlock({ block, charts, tables, cards, datasets, sources, evidenceMap, runId, viewMode }: {
  block: Record<string, unknown>;
  charts: Array<Record<string, unknown>>;
  tables: Array<Record<string, unknown>>;
  cards: Array<Record<string, unknown>>;
  datasets: Record<string, Array<Record<string, unknown>>>;
  sources: Array<Record<string, unknown>>;
  evidenceMap: Array<Record<string, unknown>>;
  runId?: string;
  viewMode?: "reading" | "evidence" | "audit";
}) {
  const type = String(block.type || "");
  const auditMeta = viewMode === "audit" && type !== "markdown" ? (
    <small className="block-audit-meta">
      id={String(block.id || "-")} type={type} renderer_target={String(block.renderer_target || "-")} block_origin={String(block.block_origin || "-")}
      {block.source_section ? ` source_section="${String(block.source_section)}"` : ""}
      {Array.isArray(block.evidence_ids) && block.evidence_ids.length ? ` evidence_ids=[${(block.evidence_ids as string[]).join(", ")}]` : ""}
    </small>
  ) : null;
  if (type === "markdown" && block.display_mode === "source_details") {
    return <>{auditMeta}<details className="visual-source-details"><summary>查看完整原文</summary><MarkdownView content={String(block.body ?? "")} /></details></>;
  }
  if (type === "markdown") return <>{auditMeta}<MarkdownView content={String(block.body ?? "")} /></>;
  if (type === "executive_storyboard") return <VisualBlockWithEvidence block={block} sources={sources} evidenceMap={evidenceMap} auditMeta={auditMeta}><VisualExecutiveStoryboard block={block} datasets={datasets} /></VisualBlockWithEvidence>;
  if (type === "adaptive_story") return <VisualBlockWithEvidence block={block} sources={sources} evidenceMap={evidenceMap} auditMeta={auditMeta}><VisualAdaptiveStory block={block} datasets={datasets} /></VisualBlockWithEvidence>;
  if (type === "kpi_grid") return <VisualBlockWithEvidence block={block} sources={sources} evidenceMap={evidenceMap} auditMeta={auditMeta}><VisualKpiGrid block={block} datasets={datasets} /></VisualBlockWithEvidence>;
  if (type === "trend_panel") return <VisualBlockWithEvidence block={block} sources={sources} evidenceMap={evidenceMap} auditMeta={auditMeta}><VisualTrendPanel block={block} datasets={datasets} /></VisualBlockWithEvidence>;
  if (type === "metric_change") return <VisualBlockWithEvidence block={block} sources={sources} evidenceMap={evidenceMap} auditMeta={auditMeta}><VisualMetricChange block={block} datasets={datasets} /></VisualBlockWithEvidence>;
  if (type === "forecast_band") return <VisualBlockWithEvidence block={block} sources={sources} evidenceMap={evidenceMap} auditMeta={auditMeta}><VisualForecastBand block={block} datasets={datasets} /></VisualBlockWithEvidence>;
  if (type === "stage_timeline") return <VisualBlockWithEvidence block={block} sources={sources} evidenceMap={evidenceMap} auditMeta={auditMeta}><VisualStageTimeline block={block} datasets={datasets} /></VisualBlockWithEvidence>;
  if (type === "comparison_grid") return <VisualBlockWithEvidence block={block} sources={sources} evidenceMap={evidenceMap} auditMeta={auditMeta}><VisualComparisonGrid block={block} datasets={datasets} /></VisualBlockWithEvidence>;
  if (type === "delta_bridge") return <VisualBlockWithEvidence block={block} sources={sources} evidenceMap={evidenceMap} auditMeta={auditMeta}><VisualDeltaBridge block={block} datasets={datasets} /></VisualBlockWithEvidence>;
  if (type === "leaderboard_pair") return <VisualBlockWithEvidence block={block} sources={sources} evidenceMap={evidenceMap} auditMeta={auditMeta}><VisualLeaderboardPair block={block} datasets={datasets} /></VisualBlockWithEvidence>;
  if (type === "composition_panel") return <VisualBlockWithEvidence block={block} sources={sources} evidenceMap={evidenceMap} auditMeta={auditMeta}><VisualCompositionPanel block={block} datasets={datasets} /></VisualBlockWithEvidence>;
  if (type === "decision_matrix") return <VisualBlockWithEvidence block={block} sources={sources} evidenceMap={evidenceMap} auditMeta={auditMeta}><VisualDecisionMatrix block={block} datasets={datasets} /></VisualBlockWithEvidence>;
  if (type === "data_quality_panel") return <VisualBlockWithEvidence block={block} sources={sources} evidenceMap={evidenceMap} auditMeta={auditMeta}><VisualDataQualityPanel block={block} datasets={datasets} /></VisualBlockWithEvidence>;
  if (type === "insight_banner") return <VisualBlockWithEvidence block={block} sources={sources} evidenceMap={evidenceMap} auditMeta={auditMeta}><VisualInsightBanner block={block} /></VisualBlockWithEvidence>;
  if (type === "risk_panel") return <VisualBlockWithEvidence block={block} sources={sources} evidenceMap={evidenceMap} auditMeta={auditMeta}><VisualRiskPanel block={block} datasets={datasets} /></VisualBlockWithEvidence>;
  if (type === "next_action_list") return <VisualBlockWithEvidence block={block} sources={sources} evidenceMap={evidenceMap} auditMeta={auditMeta}><VisualNextActionList block={block} datasets={datasets} /></VisualBlockWithEvidence>;
  if (type === "page_summary") return <VisualBlockWithEvidence block={block} sources={sources} evidenceMap={evidenceMap} auditMeta={auditMeta}><VisualPageSummary block={block} datasets={datasets} /></VisualBlockWithEvidence>;

  if (type === "chart") {
    const chartId = String(block.chart_id || block.chartId || "");
    const chart = charts.find((c) => String(c.id) === chartId);
    if (!chart) return <pre>Chart {chartId} not found</pre>;
    const datasetKey = String(chart.dataset || "");
    const rows = datasets[datasetKey] || [];
    const chartType = String(chart.type || "bar");
    return (
      <div className="report-chart">
        {auditMeta}
        <ReportVisualHeader
          title={humanizeReportLabel(String(chart.title || "图表"))}
          subtitle={String(chart.subtitle || chart.description || "")}
          unit={String(chart.unit || "")}
          rowCount={chart.render_mode === "file" ? undefined : rows.length}
          source={resolveSourceLabel(chart, sources)}
        />
        {chart.render_mode === "file" ? <FileChartPreview path={String(chart.asset_path || "")} runId={runId} title={humanizeReportLabel(String(chart.title || "图表"))} /> : rows.length > 0 ? <div className="chart-inline"><RechartsRenderer chartData={buildChartData(chart, rows)} colors={COLORS} rawData={buildHeatmapRawData(chart, rows)} compatibleTypes={toStringList(chart.compatible_types)} /></div> : <p className="chart-file-hint">图表类型: {chartType}（暂无可渲染数据）</p>}
        <ArtifactEvidenceDetails block={block} item={chart} rows={rows} sources={sources} evidenceMap={evidenceMap} />
      </div>
    );
  }

  if (type === "table") {
    const tableId = String(block.table_id || block.tableId || "");
    const table = tables.find((t) => String(t.id) === tableId);
    if (!table) return <pre>Table {tableId} not found</pre>;
    const datasetKey = String(table.dataset || "");
    const columns = toColumnList(table.columns);
    const rows = datasets[datasetKey] || [];
    return <>{auditMeta}<InlineTable title={humanizeReportLabel(String(table.title || "表格"))} subtitle={String(table.subtitle || "")} source={resolveSourceLabel(table, sources)} columns={columns} rows={rows} block={block} item={table} sources={sources} evidenceMap={evidenceMap} collapsible /></>;
  }

  if (type === "metric-strip") {
    const cardIds = Array.isArray(block.card_ids) ? (block.card_ids as string[]) : Array.isArray(block.cardIds) ? (block.cardIds as string[]) : [];
    const stripCards = cards.filter((c) => cardIds.includes(String(c.id)));
    if (stripCards.length === 0) return null;
    return (
      <VisualBlockWithEvidence block={block} sources={sources} evidenceMap={evidenceMap}>
        {auditMeta}
        <div className="report-metric-strip">{stripCards.map((card, ci) => <MetricCard key={ci} card={card} datasets={datasets} />)}</div>
      </VisualBlockWithEvidence>
    );
  }

  return <pre className="report-unknown-block">{auditMeta}Unknown block type: {type}</pre>;
}

function VisualBlockWithEvidence({ block, sources, evidenceMap, children, auditMeta }: { block: Record<string, unknown>; sources: Array<Record<string, unknown>>; evidenceMap: Array<Record<string, unknown>>; children: React.ReactNode; auditMeta?: React.ReactNode }) {
  return <div className="visual-evidence-wrapper">{auditMeta}{children}<ArtifactEvidenceDetails block={block} sources={sources} evidenceMap={evidenceMap} /></div>;
}

function MetricCard({ card, datasets }: { card: Record<string, unknown>; datasets: Record<string, Array<Record<string, unknown>>> }) {
  const cardDataset = String(card.dataset || "");
  const cardRows = datasets[cardDataset] || [];
  const cardMetrics = Array.isArray(card.metrics) ? (card.metrics as Array<{ label: string; field: string; format?: string }>) : [];
  const row = cardRows[0] || {};
  return <div className="report-metric-card">{cardMetrics.map((m, mi) => <div key={mi} className="metric-item"><span className="metric-label">{m.label}</span><span className="metric-value">{String(row[m.field] ?? "-")}</span></div>)}</div>;
}

type ReportColumn = {
  field: string;
  label: string;
  align?: string;
  format?: string;
  type?: string;
  unit?: string;
};

function ReportVisualHeader({ title, subtitle, unit, rowCount, source }: {
  title: string;
  subtitle?: string;
  unit?: string;
  rowCount?: number;
  source?: string;
}) {
  return (
    <header className="report-visual-header">
      <div>
        <h4 className="report-chart-title">{title}</h4>
        {subtitle ? <p>{subtitle}</p> : null}
      </div>
      <div className="report-visual-meta">
        {unit ? <span>单位：{unit}</span> : null}
        {rowCount != null ? <span>{rowCount} 条数据</span> : null}
        {source ? <span>来源：{source}</span> : null}
      </div>
    </header>
  );
}

function InlineTable({ title, subtitle, source, columns, rows, block, item, sources = [], evidenceMap = [], collapsible = false }: {
  title?: string;
  subtitle?: string;
  source?: string;
  columns: ReportColumn[];
  rows: Array<Record<string, unknown>>;
  block?: Record<string, unknown>;
  item?: Record<string, unknown>;
  sources?: Array<Record<string, unknown>>;
  evidenceMap?: Array<Record<string, unknown>>;
  collapsible?: boolean;
}) {
  const tableBody = (
    <>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>{columns.map((column) => <th className={columnClass(column, rows)} key={column.field}>{column.label}{column.unit ? <small>{column.unit}</small> : null}</th>)}</tr>
          </thead>
          <tbody>
            {rows.map((row, rowIndex) => (
              <tr key={rowIndex}>
                {columns.map((column) => <td className={columnClass(column, rows)} key={column.field}>{formatCell(row[column.field])}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ArtifactEvidenceDetails block={block} item={item} rows={rows} columns={columns} sources={sources} evidenceMap={evidenceMap} />
    </>
  );

  if (collapsible && title) {
    return (
      <details className="report-table report-table-details">
        <summary>
          <span><Table2 size={15} />{title}</span>
          <small>{rows.length} 条数据</small>
        </summary>
        {(subtitle || source) ? <p className="report-table-detail-note">{[subtitle, source ? `来源：${source}` : ""].filter(Boolean).join(" · ")}</p> : null}
        {tableBody}
      </details>
    );
  }

  return (
    <div className="report-table">
      {title ? <ReportVisualHeader title={title} subtitle={subtitle} rowCount={rows.length} source={source} /> : null}
      {tableBody}
    </div>
  );
}

function FileChartPreview({ path, runId, title }: { path: string; runId?: string; title: string }) {
  const filename = path.split(/[\\/]/).pop() || "";
  const extension = filename.split(".").pop()?.toLowerCase() || "";
  const assetUrl = runId && filename ? resolveApiUrl(`/api/runs/${runId}/assets/${encodeURIComponent(filename)}`) : "";

  if (assetUrl && ["png", "jpg", "jpeg", "svg"].includes(extension)) {
    return <figure className="chart-file-preview"><img alt={title} loading="lazy" src={assetUrl} /><figcaption>{filename}</figcaption></figure>;
  }
  if (assetUrl && extension === "html") {
    return (
      <figure className="chart-file-preview chart-file-preview--html">
        <iframe loading="lazy" referrerPolicy="no-referrer" sandbox="allow-scripts" src={assetUrl} title={title} />
        <a className="chart-original-link" href={assetUrl} rel="noreferrer" target="_blank" title="打开原始交互图表">
          <ExternalLink size={14} />
          <span>原始图表</span>
        </a>
      </figure>
    );
  }
  return <div className="chart-file-preview chart-file-preview--fallback"><p>图表文件暂时无法预览。</p>{filename ? <code>{filename}</code> : null}</div>;
}

function TableWidget({ artifact }: { artifact: Artifact }) {
  const tableData = asTableData(artifact.data);
  return <article className="artifact-widget"><WidgetHeader artifact={artifact} />{tableData ? <InlineTable columns={tableData.columns.map((c) => ({ field: c.key, label: c.label }))} rows={tableData.rows} /> : <pre>{artifact.content}</pre>}</article>;
}

function ChartWidget({ artifact, runId }: { artifact: Artifact; runId?: string }) {
  const data = artifact.data as JsonRecord | undefined;
  if (data?.render_mode === "file") return <article className="artifact-widget"><WidgetHeader artifact={artifact} /><div className="chart-widget chart-widget--file"><FileChartPreview path={typeof data.path === "string" ? data.path : ""} runId={runId} title={artifact.title} /></div></article>;
  const chartData = asChartData(data);
  return <article className="artifact-widget"><WidgetHeader artifact={artifact} />{chartData ? <div className="chart-widget"><div className="chart-meta"><span>{chartData.source ?? "本次运行"}</span><span>{chartData.description ?? "结构化图表产物"}</span></div><RechartsRenderer chartData={chartData} colors={COLORS} rawData={data} /></div> : <pre>{artifact.content}</pre>}</article>;
}

function RunLogWidget({ artifact }: { artifact: Artifact }) {
  const steps = Array.isArray(artifact.data?.workflow_steps) ? (artifact.data.workflow_steps as WorkflowStep[]) : [];
  const calls = Array.isArray(artifact.data?.tool_calls) ? (artifact.data.tool_calls as ToolCall[]) : [];
  const validationResults = Array.isArray(artifact.data?.validation_results) ? (artifact.data.validation_results as ValidationResult[]) : [];
  const validationPassed = artifact.data?.validation_passed as boolean | undefined;
  const candidateAngles = (artifact.data?.candidate_angles as CandidateAngle[]) || [];
  const manifest = artifact.data?.manifest as Record<string, any> | undefined;
  if (manifest && candidateAngles.length > 0) {
    const angleEvidenceCount: Record<string, number> = {};
    const items = [...((manifest.blocks as any[]) || []), ...((manifest.charts as any[]) || []), ...((manifest.tables as any[]) || [])];
    for (const item of items) for (const aid of ((item.linked_angle_ids as string[]) || [])) angleEvidenceCount[aid] = (angleEvidenceCount[aid] || 0) + 1;
    for (const angle of candidateAngles) angle.linked_evidence_count = angleEvidenceCount[angle.id] || 0;
  }
  return <article className="artifact-widget"><WidgetHeader artifact={artifact} />{validationResults.length > 0 && <ValidationGate results={validationResults} passed={validationPassed} />}{candidateAngles.length > 0 && <CandidateAnglePanel angles={candidateAngles} />}<WorkflowList steps={steps} /><div className="tool-call-list">{calls.map((call, index) => <div className="tool-call-row" key={`${call.name}-${index}`}><strong>{call.name}</strong><span>{call.status}</span><p>{call.output_summary || call.input_summary}</p></div>)}</div></article>;
}

function FileArtifactWidget({ artifact, runId }: { artifact: Artifact; runId?: string }) {
  if (isWebReportArtifact(artifact) && runId) {
    return <WebReportPreviewWidget artifact={artifact} runId={runId} />;
  }

  return <article className="artifact-widget"><WidgetHeader artifact={artifact} /><div className="file-artifact">{artifact.path}</div></article>;
}

export function isWebReportArtifact(artifact: Pick<Artifact, "title" | "type" | "data">) {
  return artifact.title === "网页版报告"
    || artifact.data?.renderer === "delivery_renderer_v0"
    || artifact.data?.renderer === "quarto_html"
    || (artifact.type === "html_report" && artifact.data?.renderer === "quarto_html");
}

export function webReportAssetUrl(artifact: Pick<Artifact, "path">, runId?: string) {
  const filename = artifact.path ? artifact.path.split(/[\\/]/).pop() || "" : "";
  return runId && filename ? resolveApiUrl(`/api/runs/${runId}/assets/${encodeURIComponent(filename)}`) : "";
}

function WebReportPreviewWidget({ artifact, runId }: { artifact: Artifact; runId: string }) {
  const assetUrl = webReportAssetUrl(artifact, runId);

  async function handleDownloadHtml() {
    if (!assetUrl) return;
    try {
      const response = await apiFetch(assetUrl);
      if (!response.ok) throw new Error("下载失败");
      const blob = await response.blob();
      downloadBlob(blob, `${safeFilename(artifact.title || "web-report")}.html`);
    } catch (error) {
      alert(error instanceof Error ? error.message : "下载 HTML 失败");
    }
  }

  if (!assetUrl) {
    return <article className="artifact-widget"><WidgetHeader artifact={artifact} /><EmptyState text="网页版报告缺少可预览的 HTML 文件。" /></article>;
  }

  return (
    <article className="artifact-widget web-report-widget">
      <div className="report-actionbar web-report-actionbar">
        <WidgetHeader artifact={artifact} />
        <button className="ghost-button export-button" onClick={handleDownloadHtml} type="button">
          <FileCode size={16} /> 下载 HTML
        </button>
      </div>
      <div className="web-report-preview-shell">
        <iframe
          className="web-report-preview-frame"
          loading="lazy"
          sandbox="allow-scripts"
          src={assetUrl}
          title={artifact.title || "网页版报告"}
        />
      </div>
    </article>
  );
}

function ManifestFooter({ sources, evidenceMap }: { sources: Array<Record<string, unknown>>; evidenceMap: Array<Record<string, unknown>> }) {
  return <footer className="manifest-footer">{sources.length > 0 && <details className="manifest-sources-section"><summary>数据来源 ({sources.length})</summary><ul className="manifest-source-list">{sources.map((s, i) => <li key={i}><strong>{String(s.label || "未知来源")}</strong>{isRecord(s.query) && s.query.description ? <span className="source-desc"> — {String(s.query.description)}</span> : null}</li>)}</ul></details>}{evidenceMap.length > 0 && <details className="manifest-evidence-section"><summary>证据溯源 ({evidenceMap.length})</summary><ul className="manifest-evidence-list">{evidenceMap.map((e, i) => <li key={i}><span className={`evidence-type-badge evidence-type-${String(e.type || "table")}`}>{e.type === "chart" ? <BarChart3 size={14} /> : e.type === "table" ? <Table2 size={14} /> : <Link2 size={14} />}</span><strong>{String(e.title || "?")}</strong>{e.source_dataset ? <span className="evidence-source"> — 来源: {String(e.source_dataset)}</span> : null}{e.row_count != null ? <span className="evidence-rows"> ({String(e.row_count)} 行)</span> : null}{e.step_id ? <span className="evidence-step"> — 步骤: {String(e.step_id)}</span> : null}</li>)}</ul></details>}</footer>;
}

export function getBlockRendererTarget(block: Record<string, unknown>): RendererTarget | undefined {
  const rt = block.renderer_target;
  if (typeof rt === "string" && (rt === "md_visual" || rt === "evidence_component" || rt === "appendix" || rt === "narrative")) {
    return rt as RendererTarget;
  }
  // Legacy block without renderer_target: infer from type.
  const type = String(block.type || "");
  if (type === "markdown") return "narrative";
  if (type === "chart" || type === "table" || type === "metric-strip") return "evidence_component";
  return undefined;
}

export function filterBlocksByMode(
  blocks: Array<Record<string, unknown>>,
  mode: "reading" | "evidence" | "audit",
): Array<Record<string, unknown>> {
  if (mode === "audit") return blocks;

  return blocks.filter((block) => {
    const target = getBlockRendererTarget(block);
    if (mode === "reading") {
      // Show narrative, md_visual, and evidence_component that are visually meaningful.
      if (target === "narrative" || target === "md_visual") return true;
      if (target === "evidence_component") {
        const type = String(block.type || "");
        return type === "chart" || type === "metric-strip" || type === "executive_storyboard"
          || type === "adaptive_story" || type === "kpi_grid" || type === "trend_panel"
          || type === "metric_change" || type === "forecast_band" || type === "delta_bridge"
          || type === "leaderboard_pair" || type === "composition_panel" || type === "decision_matrix";
      }
      return false;
    }
    // evidence mode: evidence_component + appendix (supplementary evidence layer).
    return target === "evidence_component" || target === "appendix";
  });
}

function pickVisualReportArtifact(artifacts: Artifact[]): Artifact | undefined { return artifacts.find((artifact) => artifact.type === "visual_report"); }
function sortArtifactsForReportReading(artifacts: Artifact[]): Artifact[] {
  const rank = (artifact: Artifact) => artifact.type === "visual_report" ? 0 : artifact.type === "structured_report" || artifact.type === "markdown_report" ? 1 : artifact.type === "chart" || artifact.type === "table" ? 2 : artifact.type === "run_log" ? 3 : 4;
  return [...artifacts].sort((a, b) => rank(a) - rank(b));
}

type VisualReportModel = { manifest: Record<string, unknown>; blocks: Array<Record<string, unknown>>; charts: Array<Record<string, unknown>>; tables: Array<Record<string, unknown>>; cards: Array<Record<string, unknown>>; datasets: Record<string, Array<Record<string, unknown>>>; sources: Array<Record<string, unknown>>; evidenceMap: Array<Record<string, unknown>>; };

function buildVisualReportModel(manifest: Record<string, unknown>, snapshot: Record<string, unknown>): VisualReportModel {
  return { manifest, blocks: Array.isArray(manifest.blocks) ? (manifest.blocks as Array<Record<string, unknown>>) : [], charts: Array.isArray(manifest.charts) ? (manifest.charts as Array<Record<string, unknown>>) : [], tables: Array.isArray(manifest.tables) ? (manifest.tables as Array<Record<string, unknown>>) : [], cards: Array.isArray(manifest.cards) ? (manifest.cards as Array<Record<string, unknown>>) : [], datasets: (snapshot.datasets as Record<string, Array<Record<string, unknown>>>) || {}, sources: Array.isArray(manifest.sources) ? (manifest.sources as Array<Record<string, unknown>>) : [], evidenceMap: Array.isArray(snapshot.evidence_map) ? (snapshot.evidence_map as Array<Record<string, unknown>>) : [] };
}
function isRecord(value: unknown): value is Record<string, unknown> { return typeof value === "object" && value !== null && !Array.isArray(value); }
function toRecordList(value: unknown): Array<Record<string, unknown>> { return Array.isArray(value) ? value.filter(isRecord) : []; }
function resolveSourceLabel(item: Record<string, unknown>, sources: Array<Record<string, unknown>>): string {
  const sourceId = String(item.source_id || "");
  const source = sources.find((entry) => String(entry.id || "") === sourceId);
  return String(source?.label || source?.path || sourceId || "");
}
function columnClass(column: ReportColumn, rows: Array<Record<string, unknown>>): string {
  if (column.align === "right" || column.type === "number") return "numeric";
  const values = rows.slice(0, 12).map((row) => row[column.field]).filter((value) => value !== null && value !== undefined && value !== "");
  return values.length > 0 && values.every((value) => typeof value === "number" || !Number.isNaN(Number(value))) ? "numeric" : "";
}
function toColumnList(value: unknown): ReportColumn[] { if (!Array.isArray(value)) return []; return value.filter(isRecord).map((column) => { const field = String(column.field ?? column.key ?? ""); const rawLabel = String(column.label ?? field); return { field, label: rawLabel === field ? humanizeReportLabel(rawLabel) : rawLabel, align: column.align ? String(column.align) : undefined, format: column.format ? String(column.format) : undefined, type: column.type ? String(column.type) : undefined, unit: column.unit ? String(column.unit) : undefined }; }).filter((column) => column.field); }
function toStringList(value: unknown): string[] { return Array.isArray(value) ? value.map(String).filter(Boolean) : []; }
function downloadBlob(blob: Blob, filename: string) { const url = URL.createObjectURL(blob); const a = document.createElement("a"); a.href = url; a.download = filename; a.click(); URL.revokeObjectURL(url); }
function safeFilename(name: string): string { return (name || "report").replace(/[\\/:*?"<>|]+/g, "-").replace(/\s+/g, "-").slice(0, 90) || "report"; }
function createStandaloneHtml(node: HTMLElement, title: string): string { const styleLinks = Array.from(document.querySelectorAll('link[rel="stylesheet"]')).map((link) => (link as HTMLLinkElement).outerHTML).join("\n"); const inlineStyles = Array.from(document.querySelectorAll("style")).map((style) => style.outerHTML).join("\n"); return ["<!doctype html>", '<html lang="zh-CN">', "<head>", '<meta charset="utf-8">', '<meta name="viewport" content="width=device-width, initial-scale=1">', `<title>${escapeHtml(title)}</title>`, styleLinks, inlineStyles, "</head>", '<body class="artifact-export-page">', node.outerHTML, "</body>", "</html>"].join("\n"); }
function escapeHtml(value: string): string { return value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;"); }
