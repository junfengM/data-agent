import React, { useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  Bot,
  ChevronDown,
  ChevronRight,
  Download,
  FileText,
  RefreshCw,
  Wrench,
} from "lucide-react";
import type { JsonRecord, RunResponse, RunSummary } from "../types";
import { apiFetch, resolveApiUrl } from "../apiClient";
import { fetchRuns } from "../api/runs";
import { EmptyState, PanelHeader } from "../shared";

export type TraceEvent = {
  id: string;
  order: number;
  parent_id?: string | null;
  type: string;
  name: string;
  status: string;
  summary?: string | null;
  data: JsonRecord;
  created_at?: string | null;
  elapsed_ms?: number | null;
  source?: "runtime" | "derived";
};

type DiagnosticSummary = {
  status: string;
  event_count: number;
  llm_call_count: number;
  analysis_execution_count: number;
  failed_event_count: number;
  validation_failure_count: number;
  validation_passed?: boolean | null;
  likely_failure_stage?: string | null;
  likely_failure_mode?: string | null;
  final_report_chars?: number;
  llm_length_truncation_count?: number;
  detached_finalizer_used?: boolean;
  table_artifact_count?: number;
  chart_artifact_count?: number;
  evidence_generation_completed?: boolean;
  empty_or_tiny_report?: boolean;
  force_finalize_used?: boolean;
  validation_failed_gates?: string[];
  recommended_debug_focus?: string[];
};

type RunTrace = {
  run: RunSummary;
  events: TraceEvent[];
  event_count: number;
  schema_version: number;
  diagnostic_summary?: DiagnosticSummary;
};

type TraceModuleProps = {
  currentRun: RunResponse | null;
  onOpenRun: (runId: string) => void;
  selectedProjectId: string;
};

type TraceView = "timeline" | "llm";

export default function TraceModule({ currentRun, onOpenRun, selectedProjectId }: TraceModuleProps) {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [selectedRunId, setSelectedRunId] = useState(currentRun?.id ?? "");
  const [trace, setTrace] = useState<RunTrace | null>(null);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [filter, setFilter] = useState<"all" | "llm" | "tools" | "errors">("all");
  const [traceView, setTraceView] = useState<TraceView>("timeline");
  const [isLoadingRuns, setIsLoadingRuns] = useState(false);
  const [isLoadingTrace, setIsLoadingTrace] = useState(false);

  useEffect(() => {
    if (currentRun?.id) setSelectedRunId(currentRun.id);
  }, [currentRun?.id]);

  useEffect(() => {
    setSelectedRunId("");
    setTrace(null);
    loadRuns();
  }, [selectedProjectId]);

  useEffect(() => {
    if (selectedRunId) loadTrace(selectedRunId);
    else setTrace(null);
  }, [selectedRunId]);

  useEffect(() => {
    if (!selectedRunId || trace?.run.status !== "running") return;
    const timer = window.setInterval(() => {
      loadTrace(selectedRunId);
      loadRuns();
    }, 2500);
    return () => window.clearInterval(timer);
  }, [selectedRunId, trace?.run.status]);

  const visibleEvents = useMemo(
    () => (trace?.events ?? []).filter((event) => matchesFilter(event, filter)),
    [trace, filter],
  );
  const executionChain = useMemo(
    () => buildExecutionChain(trace?.events ?? []),
    [trace],
  );
  const llmLog = useMemo(
    () => buildLlmTuningLog(trace),
    [trace],
  );

  async function loadRuns() {
    setIsLoadingRuns(true);
    try {
      const payload = await fetchRuns(selectedProjectId || undefined);
      setRuns(payload);
      setSelectedRunId((current) =>
        current && payload.some((run) => run.id === current)
          ? current
          : currentRun?.id && payload.some((run) => run.id === currentRun.id)
            ? currentRun.id
            : payload[0]?.id || ""
      );
    } catch {
      setRuns([]);
    } finally {
      setIsLoadingRuns(false);
    }
  }

  async function loadTrace(runId: string) {
    setIsLoadingTrace(true);
    try {
      const query = selectedProjectId ? `?project_id=${encodeURIComponent(selectedProjectId)}` : "";
      const response = await apiFetch(`/api/runs/${runId}/trace${query}`);
      if (!response.ok) throw new Error("Failed to load trace");
      setTrace((await response.json()) as RunTrace);
    } catch {
      setTrace(null);
    } finally {
      setIsLoadingTrace(false);
    }
  }

  function toggle(eventId: string) {
    setExpanded((current) => ({ ...current, [eventId]: !current[eventId] }));
  }

  return (
    <div className="trace-layout">
      <aside className="trace-rail">
        <PanelHeader title="任务回放" subtitle={selectedProjectId ? "当前项目运行" : "全部运行"} />
        <button className="ghost-button" onClick={loadRuns} type="button" disabled={isLoadingRuns}>
          <RefreshCw size={14} /> 刷新任务
        </button>
        {selectedRunId && runs.find((run) => run.id === selectedRunId)?.has_visual_report ? (
          <button className="primary-button trace-open-report" onClick={() => onOpenRun(selectedRunId)} type="button">
            <FileText size={14} /> 打开所选报告
          </button>
        ) : null}
        {selectedRunId ? (
          <>
            <a
              className="ghost-button trace-export"
              href={resolveApiUrl(`/api/runs/${selectedRunId}/trace/export?level=normal${selectedProjectId ? `&project_id=${encodeURIComponent(selectedProjectId)}` : ""}`)}
              download
            >
              <Download size={14} /> 导出诊断包 normal
            </a>
            <a
              className="ghost-button trace-export"
              href={resolveApiUrl(`/api/runs/${selectedRunId}/trace/export?level=diagnostic${selectedProjectId ? `&project_id=${encodeURIComponent(selectedProjectId)}` : ""}`)}
              download
            >
              <Download size={14} /> 导出诊断包 diagnostic
            </a>
          </>
        ) : null}
        {runs.length ? (
          <div className="trace-run-list">
            {runs.map((run) => (
              <button
                className={`trace-run-item ${run.id === selectedRunId ? "selected" : ""}`}
                key={run.id}
                onClick={() => setSelectedRunId(run.id)}
                type="button"
              >
                <strong>{run.question}</strong>
                <span>Run {run.id.slice(0, 8)} · {run.status}</span>
                <small>
                  {run.tool_call_count} tools · {run.artifact_count} artifacts
                  {hasVisualReport(run) ? " · 图文报告" : ""}
                </small>
              </button>
            ))}
          </div>
        ) : (
          <EmptyState text="暂无可回放任务。先运行一次分析。" />
        )}
      </aside>

      <section className="trace-stage">
        <PanelHeader
          title="执行链路"
          subtitle={trace ? `${trace.event_count} 个事件 · schema v${trace.schema_version}` : "选择一个任务查看链路"}
        />
        {isLoadingTrace ? <EmptyState text="正在加载任务链路…" /> : null}
        {!isLoadingTrace && trace ? (
          <div className="trace-content">
            <section className="trace-diagnostics">
              <DiagnosticCard label="LLM 调用" value={trace.diagnostic_summary?.llm_call_count ?? 0} icon={<Bot size={16} />} />
              <DiagnosticCard label="代码执行" value={trace.diagnostic_summary?.analysis_execution_count ?? 0} icon={<Wrench size={16} />} />
              <DiagnosticCard label="失败事件" value={trace.diagnostic_summary?.failed_event_count ?? 0} icon={<AlertTriangle size={16} />} danger />
              <DiagnosticCard label="校验失败" value={trace.diagnostic_summary?.validation_failure_count ?? 0} icon={<Activity size={16} />} />
              <DiagnosticCard label="Length 截断" value={trace.diagnostic_summary?.llm_length_truncation_count ?? 0} icon={<AlertTriangle size={16} />} danger />
              <DiagnosticCard label="报告字数" value={trace.diagnostic_summary?.final_report_chars ?? 0} icon={<FileText size={16} />} danger={Boolean(trace.diagnostic_summary?.empty_or_tiny_report)} />
              <DiagnosticCard label="证据表/图" value={`${trace.diagnostic_summary?.table_artifact_count ?? 0}/${trace.diagnostic_summary?.chart_artifact_count ?? 0}`} icon={<FileText size={16} />} />
            </section>
            {executionChain.length ? <ExecutionChainView phases={executionChain} /> : null}
            {trace.diagnostic_summary?.likely_failure_mode ? (
              <section className="trace-failure-analysis">
                <div className="trace-failure-item">
                  <AlertTriangle size={14} />
                  <span>可能失败阶段：{trace.diagnostic_summary.likely_failure_stage ?? "—"}</span>
                </div>
                <div className="trace-failure-item">
                  <AlertTriangle size={14} />
                  <span>可能失败模式：{trace.diagnostic_summary.likely_failure_mode}</span>
                </div>
                {trace.diagnostic_summary.detached_finalizer_used ? (
                  <div className="trace-failure-item">
                    <span>已使用分离式收口</span>
                  </div>
                ) : null}
                {trace.diagnostic_summary.force_finalize_used ? (
                  <div className="trace-failure-item">
                    <span>已使用强制收口</span>
                  </div>
                ) : null}
                {(trace.diagnostic_summary.validation_failed_gates?.length ?? 0) > 0 ? (
                  <div className="trace-failure-item">
                    <span>校验失败门：{trace.diagnostic_summary.validation_failed_gates!.join("、")}</span>
                  </div>
                ) : null}
                {(trace.diagnostic_summary.recommended_debug_focus?.length ?? 0) > 0 ? (
                  <div className="trace-failure-item">
                    <span>建议排查：{trace.diagnostic_summary.recommended_debug_focus!.join(" → ")}</span>
                  </div>
                ) : null}
              </section>
            ) : null}
            <div className="trace-view-tabs" aria-label="任务回放视图">
              <button className={traceView === "timeline" ? "selected" : ""} onClick={() => setTraceView("timeline")} type="button">
                执行事件
              </button>
              <button className={traceView === "llm" ? "selected" : ""} onClick={() => setTraceView("llm")} type="button">
                LLM 调优
              </button>
            </div>
            {traceView === "timeline" ? (
              <>
                <div className="trace-filters" aria-label="执行事件筛选">
                  {(["all", "llm", "tools", "errors"] as const).map((item) => (
                    <button
                      className={filter === item ? "selected" : ""}
                      key={item}
                      onClick={() => setFilter(item)}
                      type="button"
                    >
                      {filterLabel(item)}
                    </button>
                  ))}
                  <span>{visibleEvents.length} / {trace.event_count} 个事件</span>
                </div>
                <div className="trace-timeline">
                  {visibleEvents.map((event) => (
                    <article className={`trace-event trace-event--${event.status}`} key={event.id}>
                      <button className="trace-event-header" onClick={() => toggle(event.id)} type="button">
                        {expanded[event.id] ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                        <Activity size={15} />
                        <span className="trace-event-order">#{event.order}</span>
                        <strong>{event.name}</strong>
                        {event.elapsed_ms != null ? (
                          <span className="trace-event-time">{formatElapsed(event.elapsed_ms)}</span>
                        ) : null}
                        <span className="trace-event-type">{eventTypeLabel(event.type)}</span>
                        <span className="trace-event-status">{event.status}</span>
                      </button>
                      {event.summary ? <p className="trace-event-summary">{event.summary}</p> : null}
                      {expanded[event.id] ? (
                        <div className="trace-event-detail">
                          <div className="trace-event-meta">
                            <span>来源：{event.source === "runtime" ? "运行时记录" : "最终产物推导"}</span>
                            {event.created_at ? <span>记录时间：{event.created_at}</span> : null}
                            {event.elapsed_ms != null ? <span>距启动：{formatElapsed(event.elapsed_ms)}</span> : null}
                          </div>
                          <pre className="trace-event-data">{JSON.stringify(event.data, null, 2)}</pre>
                        </div>
                      ) : null}
                    </article>
                  ))}
                </div>
              </>
            ) : (
              <LlmTuningPanel log={llmLog} projectId={selectedProjectId} runId={selectedRunId} />
            )}
          </div>
        ) : null}
        {!isLoadingTrace && !trace ? <EmptyState text="没有可展示的执行链路。" /> : null}
      </section>
    </div>
  );
}

type PreviewValue = {
  chars?: number;
  head?: string;
  tail?: string;
  truncated?: boolean;
};

type PromptSnapshotMessage = {
  index?: number;
  role?: string;
  content_chars?: number;
  content_preview?: string | PreviewValue;
  tool_calls?: Array<Record<string, unknown>>;
};

export type LlmRound = {
  iteration: number;
  phase: string;
  status: string;
  model: string;
  startedOrder?: number;
  completedOrder?: number;
  latencyMs?: number;
  finishReason?: string;
  usage: Record<string, unknown>;
  contextBudget: Record<string, unknown>;
  inputMetrics: Record<string, unknown>;
  availableTools: string[];
  promptSnapshot?: {
    message_count?: number;
    included_message_count?: number;
    omitted_message_count?: number;
    total_content_chars?: number;
    messages?: PromptSnapshotMessage[];
  };
  response: Record<string, unknown>;
  toolRequests: Array<Record<string, unknown>>;
  toolResults: Array<Record<string, unknown>>;
};

export type LlmTuningLog = {
  requestCount: number;
  totalPromptTokens: number;
  totalCompletionTokens: number;
  totalLatencyMs: number;
  lengthTruncationCount: number;
  toolRequestCount: number;
  toolFailureCount: number;
  maxContextChars: number;
  maxMessageCount: number;
  rounds: LlmRound[];
  notes: Array<{ severity: string; title: string; detail: string }>;
};

export function buildLlmTuningLog(trace: RunTrace | null): LlmTuningLog {
  const rounds = new Map<number, LlmRound>();
  let totalPromptTokens = 0;
  let totalCompletionTokens = 0;
  let totalLatencyMs = 0;
  let lengthTruncationCount = 0;
  let toolRequestCount = 0;
  let toolFailureCount = 0;
  let maxContextChars = 0;
  let maxMessageCount = 0;

  for (const event of trace?.events ?? []) {
    const data = event.data ?? {};
    const iteration = numberValue(data.iteration);
    const round = iteration != null ? ensureLlmRound(rounds, iteration) : null;

    if (event.type === "llm_request_started" && round) {
      round.startedOrder = event.order;
      round.phase = stringValue(data.phase) || round.phase;
      round.model = stringValue(data.model) || stringValue(recordValue(data.model_config)?.model) || round.model;
      round.contextBudget = recordValue(data.context_budget) ?? {
        estimated_context_chars: data.estimated_context_chars,
        message_count: data.message_count,
      };
      round.inputMetrics = {
        message_count: data.message_count,
        prompt_chars: data.prompt_chars,
        message_content_chars: data.message_content_chars ?? data.prompt_message_chars,
        tool_call_argument_chars: data.tool_call_argument_chars ?? data.prompt_tool_argument_chars,
        tool_result_chars: data.tool_result_chars,
        estimated_context_chars: data.estimated_context_chars,
        context_budget_action: data.context_budget_action,
        execution_count: data.execution_count,
        feedback_rounds: data.feedback_rounds,
      };
      round.availableTools = arrayOfStrings(data.available_tools);
      round.promptSnapshot = promptSnapshotValue(data.prompt_snapshot);
      maxContextChars = Math.max(maxContextChars, numberValue(data.estimated_context_chars) ?? numberValue(round.contextBudget.estimated_context_chars) ?? 0);
      maxMessageCount = Math.max(maxMessageCount, numberValue(data.message_count) ?? numberValue(round.contextBudget.message_count) ?? 0);
    }

    if (event.type === "llm_request_completed" && round) {
      round.completedOrder = event.order;
      round.phase = stringValue(data.phase) || round.phase;
      round.latencyMs = numberValue(data.latency_ms ?? data.duration_ms) ?? round.latencyMs;
      round.finishReason = stringValue(data.finish_reason) || round.finishReason;
      round.usage = recordValue(data.usage) ?? {};
      round.response = {
        content_chars: data.content_chars,
        content_preview: data.content_preview,
        requested_tool_names: data.requested_tool_names ?? data.requested_tools,
        tool_arguments: data.tool_arguments,
        response_id: data.response_id,
      };
      totalPromptTokens += numberValue(round.usage.prompt_tokens) ?? 0;
      totalCompletionTokens += numberValue(round.usage.completion_tokens) ?? 0;
      totalLatencyMs += round.latencyMs ?? 0;
      if (round.finishReason === "length") lengthTruncationCount += 1;
    }

    if (event.type === "llm_request_failed" && round) {
      round.status = "failed";
      round.response = {
        error_type: data.error_type,
        error: data.error,
      };
    }

    if (event.type === "planner_tool_requested" && round) {
      toolRequestCount += 1;
      round.toolRequests.push({
        order: event.order,
        tool: data.tool,
        arguments: data.arguments,
        summary: event.summary,
      });
    }

    if ((event.type === "planner_tool_completed" || event.type === "planner_tool_failed") && round) {
      if (event.type === "planner_tool_failed") toolFailureCount += 1;
      round.toolResults.push({
        order: event.order,
        type: event.type,
        tool: data.tool,
        result: data.result,
        error_type: data.error_type,
        error: data.error,
        summary: event.summary,
      });
    }
  }

  const sortedRounds = [...rounds.values()].sort((a, b) => a.iteration - b.iteration);
  return {
    requestCount: sortedRounds.length,
    totalPromptTokens,
    totalCompletionTokens,
    totalLatencyMs,
    lengthTruncationCount,
    toolRequestCount,
    toolFailureCount,
    maxContextChars,
    maxMessageCount,
    rounds: sortedRounds,
    notes: buildLlmNotes(sortedRounds, {
      lengthTruncationCount,
      toolFailureCount,
      maxContextChars,
    }),
  };
}

function ensureLlmRound(rounds: Map<number, LlmRound>, iteration: number): LlmRound {
  const existing = rounds.get(iteration);
  if (existing) return existing;
  const created: LlmRound = {
    iteration,
    phase: "analysis",
    status: "completed",
    model: "",
    usage: {},
    contextBudget: {},
    inputMetrics: {},
    availableTools: [],
    response: {},
    toolRequests: [],
    toolResults: [],
  };
  rounds.set(iteration, created);
  return created;
}

function buildLlmNotes(rounds: LlmRound[], metrics: { lengthTruncationCount: number; toolFailureCount: number; maxContextChars: number }) {
  const notes: LlmTuningLog["notes"] = [];
  if (!rounds.length) {
    notes.push({ severity: "warning", title: "没有 LLM 调用记录", detail: "该运行可能没有进入模型规划阶段，或来自旧版本日志。" });
  }
  if (metrics.lengthTruncationCount > 0) {
    notes.push({ severity: "risk", title: "模型输出被截断", detail: "优先检查 max_tokens、finalizer 输出格式约束和上下文压缩策略。" });
  }
  if (metrics.toolFailureCount > 0) {
    notes.push({ severity: "risk", title: "存在工具调用失败", detail: "重点查看失败轮次的工具参数和后续 repair 是否收敛。" });
  }
  if (metrics.maxContextChars >= 80_000) {
    notes.push({ severity: "warning", title: "上下文接近高水位", detail: "优先压缩工具结果、数据画像和历史消息。" });
  }
  if (!rounds.some((round) => round.promptSnapshot)) {
    notes.push({ severity: "info", title: "缺少 prompt 快照", detail: "旧运行不会记录 prompt_snapshot；新运行会显示有界 prompt 预览。" });
  }
  return notes;
}

function LlmTuningPanel({ log, projectId, runId }: { log: LlmTuningLog; projectId: string; runId: string }) {
  const exportQuery = projectId ? `?project_id=${encodeURIComponent(projectId)}` : "";
  return (
    <section className="llm-tuning-panel">
      <div className="llm-tuning-header">
        <div>
          <h3>LLM 调优链路</h3>
          <p>按模型调用轮次串起提示词、模型判断、工具动作和结果反馈，用来复盘完整分析过程。</p>
        </div>
        {runId ? (
          <a className="ghost-button trace-export" href={resolveApiUrl(`/api/runs/${runId}/trace/llm/export${exportQuery}`)} download>
            <Download size={14} /> 导出 LLM 日志
          </a>
        ) : null}
      </div>

      {log.notes.length ? (
        <section className="llm-note-list">
          {log.notes.map((note) => (
            <article className={`llm-note llm-note--${note.severity}`} key={`${note.title}-${note.detail}`}>
              <strong>{note.title}</strong>
              <p>{note.detail}</p>
            </article>
          ))}
        </section>
      ) : null}

      {log.rounds.length ? (
        <>
          <LlmVisualChain rounds={log.rounds} />
          <div className="llm-round-list">
            {log.rounds.map((round) => <LlmRoundCard key={round.iteration} round={round} />)}
          </div>
        </>
      ) : (
        <EmptyState text="当前运行没有可展示的 LLM 调优日志。" />
      )}
    </section>
  );
}

function LlmVisualChain({ rounds }: { rounds: LlmRound[] }) {
  return (
    <section className="llm-chain" aria-label="LLM 调用可视化链路">
      {rounds.map((round) => (
        <article className={`llm-chain-node llm-chain-node--${round.status}`} key={round.iteration}>
          <span className="llm-chain-index">{round.iteration}</span>
          <strong>{roundStage(round)}</strong>
          <p>{roundDecision(round)}</p>
          <small>{round.finishReason || "等待响应"} · {round.latencyMs != null ? formatElapsed(round.latencyMs) : "耗时未知"} · {round.toolRequests.length} 个工具动作</small>
        </article>
      ))}
    </section>
  );
}

function LlmRoundCard({ round }: { round: LlmRound }) {
  const promptMessages = round.promptSnapshot?.messages ?? [];
  const requestedToolNames = arrayOfStrings(round.response.requested_tool_names);
  const toolActions = toolActionItems(round);
  return (
    <article className={`llm-round-card llm-round-card--${round.status}`}>
      <header className="llm-round-header">
        <div>
          <strong>第 {round.iteration} 轮 · {roundStage(round)}</strong>
          <span>{round.model || "未知模型"}</span>
        </div>
        <div className="llm-round-badges">
          <span>{round.finishReason || "no finish_reason"}</span>
          {round.latencyMs != null ? <span>{formatElapsed(round.latencyMs)}</span> : null}
          {round.usage.total_tokens != null ? <span>{String(round.usage.total_tokens)} tokens</span> : null}
        </div>
      </header>

      <section className="llm-process-map" aria-label="本轮分析过程">
        <ProcessStep
          title="1. 输入提示词"
          body={promptMessages.length
            ? `${promptMessages.length} 条可见消息，约 ${metricText(round.promptSnapshot?.total_content_chars ?? round.inputMetrics.message_content_chars ?? round.inputMetrics.prompt_chars)} 字符。`
            : "这个历史运行没有记录 prompt 快照；新运行会显示有界提示词预览。"}
        />
        <ProcessStep
          title="2. 模型判断"
          body={roundDecision(round)}
        />
        <ProcessStep
          title="3. 工具动作"
          body={requestedToolNames.length
            ? `模型请求：${requestedToolNames.map(toolDisplayName).join("、")}`
            : toolActions.length
              ? `本轮记录了 ${toolActions.length} 个工具动作。`
              : "本轮没有请求工具，通常表示模型在整理回答或进入收口。"}
        />
        <ProcessStep
          title="4. 结果反馈"
          body={roundResultSummary(round)}
        />
      </section>

      {promptMessages.length ? (
        <section className="llm-prompt-section">
          <header>
            <strong>本轮提示词快照</strong>
            <span>
              {round.promptSnapshot?.included_message_count ?? promptMessages.length}/{round.promptSnapshot?.message_count ?? promptMessages.length} 条消息
              {(round.promptSnapshot?.omitted_message_count ?? 0) > 0 ? ` · 中间省略 ${round.promptSnapshot?.omitted_message_count} 条` : ""}
            </span>
          </header>
          <div className="llm-prompt-list">
            {promptMessages.map((message, index) => (
              <article className="llm-prompt-message" key={`${message.index ?? index}-${message.role ?? "role"}`}>
                <header>
                  <strong>#{message.index ?? index} · {roleLabel(message.role)}</strong>
                  <span>{message.content_chars ?? 0} chars</span>
                </header>
                <p>{previewToText(message.content_preview) || "无文本内容"}</p>
                {(message.tool_calls?.length ?? 0) > 0 ? (
                  <div className="llm-tool-call-list">
                    {message.tool_calls!.map((toolCall, toolIndex) => (
                      <span key={toolIndex}>{toolDisplayName(stringValue(recordValue(toolCall.function)?.name ?? toolCall.name))}</span>
                    ))}
                  </div>
                ) : null}
              </article>
            ))}
          </div>
        </section>
      ) : null}

      {round.response.content_preview ? (
        <section className="llm-response-section">
          <strong>模型响应预览</strong>
          <p>{previewToText(round.response.content_preview)}</p>
        </section>
      ) : null}

      {toolActions.length ? (
        <section className="llm-tool-section">
          <header>
            <strong>工具决策与结果</strong>
            <span>{toolActions.length} 个动作</span>
          </header>
          <div className="llm-tool-grid">
            {toolActions.map((action, index) => (
              <article className={`llm-tool-card llm-tool-card--${action.status}`} key={`${action.tool}-${index}`}>
                <div>
                  <strong>{toolDisplayName(action.tool)}</strong>
                  <span>{action.statusLabel}</span>
                </div>
                <p>{action.summary}</p>
                {action.arguments.length ? (
                  <ul>
                    {action.arguments.map((item) => <li key={item}>{item}</li>)}
                  </ul>
                ) : null}
                {action.result ? <small>{action.result}</small> : null}
              </article>
            ))}
          </div>
        </section>
      ) : null}

    </article>
  );
}

function ProcessStep({ title, body }: { title: string; body: string }) {
  return (
    <div className="llm-process-step">
      <strong>{title}</strong>
      <p>{body}</p>
    </div>
  );
}

type ExecutionPhaseId = "prepare" | "model" | "tools" | "report" | "validation";

export type ExecutionPhase = {
  id: ExecutionPhaseId;
  title: string;
  status: string;
  summary: string;
  eventCount: number;
  firstOrder: number;
  lastOrder: number;
};

const PHASE_LABELS: Record<ExecutionPhaseId, string> = {
  prepare: "准备输入",
  model: "模型决策",
  tools: "工具与代码",
  report: "报告收口",
  validation: "验证结果",
};

export function buildExecutionChain(events: TraceEvent[]): ExecutionPhase[] {
  const grouped = new Map<ExecutionPhaseId, TraceEvent[]>();
  for (const event of events) {
    const phaseId = phaseForEvent(event);
    if (!phaseId) continue;
    grouped.set(phaseId, [...(grouped.get(phaseId) ?? []), event]);
  }

  return (["prepare", "model", "tools", "report", "validation"] as ExecutionPhaseId[])
    .map((id) => {
      const phaseEvents = grouped.get(id) ?? [];
      if (!phaseEvents.length) return null;
      return {
        id,
        title: PHASE_LABELS[id],
        status: phaseStatus(phaseEvents),
        summary: phaseSummary(id, phaseEvents),
        eventCount: phaseEvents.length,
        firstOrder: Math.min(...phaseEvents.map((event) => event.order)),
        lastOrder: Math.max(...phaseEvents.map((event) => event.order)),
      };
    })
    .filter((phase): phase is ExecutionPhase => Boolean(phase));
}

function ExecutionChainView({ phases }: { phases: ExecutionPhase[] }) {
  return (
    <section className="trace-chain" aria-label="执行阶段概览">
      {phases.map((phase, index) => (
        <article className={`trace-chain-step trace-chain-step--${phase.status}`} key={phase.id}>
          <span className="trace-chain-index">{index + 1}</span>
          <div>
            <strong>{phase.title}</strong>
            <p>{phase.summary}</p>
            <small>事件 #{phase.firstOrder}–#{phase.lastOrder} · {phase.eventCount} 条</small>
          </div>
        </article>
      ))}
    </section>
  );
}

function phaseForEvent(event: TraceEvent): ExecutionPhaseId | null {
  const type = event.type;
  if (
    type === "run_started"
    || type === "context_loaded"
    || type === "dataset_profile_started"
    || type === "dataset_profile_completed"
    || type === "preflight_completed"
    || type === "planning_started"
    || type === "planning_completed"
    || type === "run"
    || type === "workflow_step"
  ) {
    return "prepare";
  }
  if (type.startsWith("report_") || type === "planner_finalized" || type === "planner_final_payload_parsed" || type === "artifact") return "report";
  if (type.startsWith("llm_") || type.startsWith("planner_final") || type === "feedback_evaluated") {
    return "model";
  }
  if (type.includes("tool") || type.startsWith("code_")) return "tools";
  if (type.startsWith("validation_") || type === "validation_summary" || type === "validation_gate") return "validation";
  return null;
}

function phaseStatus(events: TraceEvent[]) {
  if (events.some((event) => ["failed", "failure"].includes(event.status) || event.type.endsWith("_failed"))) return "failed";
  const ordered = [...events].sort((a, b) => a.order - b.order);
  const last = ordered[ordered.length - 1];
  if (last?.status === "running") return "running";
  if (events.some((event) => event.status === "warning")) return "warning";
  return "completed";
}

function phaseSummary(id: ExecutionPhaseId, events: TraceEvent[]) {
  if (id === "model") {
    const llmCalls = events.filter((event) => event.type === "llm_request_started").length
      || events.filter((event) => event.type === "llm_request_completed").length;
    const repairCount = events.filter((event) => event.type.includes("repair")).length;
    return `${llmCalls} 次模型调用${repairCount ? ` · ${repairCount} 次格式/结构修复` : ""}`;
  }
  if (id === "tools") {
    const toolCalls = events.filter((event) => event.type === "planner_tool_completed" || event.type === "tool_call").length;
    const outputCounts = events.reduce((acc, event) => {
      const tableCount = Number(event.data.table_count ?? event.data.tables_count ?? 0);
      const chartCount = Number(event.data.chart_count ?? event.data.charts_count ?? 0);
      return {
        tables: acc.tables + (Number.isFinite(tableCount) ? tableCount : 0),
        charts: acc.charts + (Number.isFinite(chartCount) ? chartCount : 0),
      };
    }, { tables: 0, charts: 0 });
    return `${toolCalls} 次工具结果 · ${outputCounts.tables} 个表格 · ${outputCounts.charts} 个图表`;
  }
  if (id === "report") {
    const parsed = events.find((event) => event.type === "planner_final_payload_parsed");
    const chars = parsed?.data.report_md_chars;
    return chars ? `最终报告结构已解析 · ${String(chars)} 字` : `${events.length} 个报告/产物事件`;
  }
  if (id === "validation") {
    const validation = [...events].reverse().find((event) => event.type === "validation_completed");
    const pass = validation?.data.pass_count;
    const total = validation?.data.gate_count ?? validation?.data.total_count;
    return pass != null && total != null ? `${String(pass)}/${String(total)} 个验证门通过` : `${events.length} 个验证事件`;
  }
  const datasetProfiles = events.filter((event) => event.type.startsWith("dataset_profile")).length;
  return datasetProfiles ? `已读取项目上下文和数据画像 · ${datasetProfiles} 个数据画像事件` : `${events.length} 个准备事件`;
}

function DiagnosticCard({
  label,
  value,
  icon,
  danger = false,
}: {
  label: string;
  value: number | string;
  icon: React.ReactNode;
  danger?: boolean;
}) {
  const isDanger = danger && (typeof value === "number" ? value > 0 : Boolean(value));
  return (
    <div className={`trace-diagnostic-card ${isDanger ? "danger" : ""}`}>
      {icon}
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function hasVisualReport(run: RunSummary) {
  return Boolean(run.has_visual_report);
}

function matchesFilter(event: TraceEvent, filter: "all" | "llm" | "tools" | "errors") {
  if (filter === "all") return true;
  if (filter === "errors") return ["failed", "failure"].includes(event.status);
  if (filter === "llm") {
    return event.type.startsWith("llm_") || event.type.startsWith("planner_") || event.type === "feedback_evaluated";
  }
  return event.type.includes("tool") || event.type.startsWith("code_");
}

function filterLabel(filter: "all" | "llm" | "tools" | "errors") {
  return {
    all: "全部",
    llm: "LLM 链路",
    tools: "工具与代码",
    errors: "仅看失败",
  }[filter];
}

function formatElapsed(milliseconds: number) {
  if (milliseconds < 1000) return `${milliseconds} ms`;
  if (milliseconds < 60_000) return `${(milliseconds / 1000).toFixed(1)} s`;
  return `${Math.floor(milliseconds / 60_000)}m ${Math.round((milliseconds % 60_000) / 1000)}s`;
}

function formatCompact(value: number) {
  if (!Number.isFinite(value)) return "0";
  if (Math.abs(value) >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (Math.abs(value) >= 1_000) return `${(value / 1_000).toFixed(1)}k`;
  return String(value);
}

function metricText(value: unknown) {
  const numeric = numberValue(value);
  if (numeric != null) return formatCompact(numeric);
  const text = stringValue(value);
  return text || "—";
}

function numberValue(value: unknown): number | undefined {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim() && Number.isFinite(Number(value))) return Number(value);
  return undefined;
}

function stringValue(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function recordValue(value: unknown): Record<string, unknown> | undefined {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? value as Record<string, unknown>
    : undefined;
}

function arrayOfStrings(value: unknown): string[] {
  return Array.isArray(value) ? value.map(String).filter(Boolean) : [];
}

function promptSnapshotValue(value: unknown): LlmRound["promptSnapshot"] {
  const record = recordValue(value);
  if (!record) return undefined;
  const rawMessages = Array.isArray(record.messages) ? record.messages : [];
  return {
    message_count: numberValue(record.message_count),
    included_message_count: numberValue(record.included_message_count),
    omitted_message_count: numberValue(record.omitted_message_count),
    total_content_chars: numberValue(record.total_content_chars),
    messages: rawMessages.filter(recordValue).map((message) => ({
      index: numberValue(message.index),
      role: stringValue(message.role),
      content_chars: numberValue(message.content_chars),
      content_preview: message.content_preview as string | PreviewValue | undefined,
      tool_calls: Array.isArray(message.tool_calls) ? message.tool_calls.filter(recordValue) : [],
    })),
  };
}

function previewToText(value: unknown): string {
  if (typeof value === "string") return value;
  const preview = recordValue(value);
  if (!preview) return "";
  const head = stringValue(preview.head);
  const tail = stringValue(preview.tail);
  if (head && tail && head !== tail) return `${head}\n...\n${tail}`;
  if (head) return head;
  return JSON.stringify(preview, null, 2);
}

function roundStage(round: LlmRound): string {
  if (round.phase === "finalize" || (!round.toolRequests.length && round.finishReason === "stop")) return "报告收口";
  if (round.phase === "repair" || round.toolResults.some((item) => stringValue(item.type).includes("failed"))) return "修复重试";
  const toolNames = [
    ...round.toolRequests.map((item) => stringValue(item.tool)),
    ...arrayOfStrings(round.response.requested_tool_names),
  ];
  if (toolNames.some((name) => name === "read_preflight")) return "读取项目上下文";
  if (toolNames.some((name) => name === "list_skills" || name === "load_skill")) return "选择并加载技能";
  if (toolNames.some((name) => name === "execute_code")) return "执行分析代码";
  if (toolNames.some((name) => name === "save_semantic_finding")) return "沉淀语义发现";
  if (toolNames.length > 0) return "选择分析工具";
  if ((numberValue(round.inputMetrics.execution_count) ?? 0) > 0) return "整合已有证据";
  return "理解问题与上下文";
}

function roundDecision(round: LlmRound): string {
  const toolNames = arrayOfStrings(round.response.requested_tool_names);
  if (round.finishReason === "length") return "模型输出触达长度上限，需要压缩输出或提高 max_tokens。";
  if (round.status === "failed") return "模型调用失败，需要查看错误和模型配置。";
  if (toolNames.length > 0) return `模型决定调用 ${toolNames.map(toolDisplayName).join("、")}。`;
  if (round.toolRequests.length > 0) return `模型发起 ${round.toolRequests.length} 个工具动作。`;
  if (round.finishReason === "stop") return "模型停止继续调用工具，开始输出或收口报告。";
  return "模型完成本轮判断，等待下一步事件。";
}

function roundResultSummary(round: LlmRound): string {
  const failures = round.toolResults.filter((item) => stringValue(item.type).includes("failed") || item.error_type);
  if (failures.length) return `${failures.length} 个工具结果失败，需要检查参数或修复提示词。`;
  if (round.toolResults.length) return `${round.toolResults.length} 个工具结果返回，供后续模型轮次继续使用。`;
  const contentChars = numberValue(round.response.content_chars);
  if (contentChars != null && contentChars > 0) return `模型返回 ${formatCompact(contentChars)} 字符内容。`;
  if (round.finishReason === "stop") return "本轮没有工具结果，模型进入最终表达。";
  return "暂无可见结果反馈。";
}

type ToolActionItem = {
  tool: string;
  status: "completed" | "failed" | "pending";
  statusLabel: string;
  summary: string;
  arguments: string[];
  result?: string;
};

function toolActionItems(round: LlmRound): ToolActionItem[] {
  const count = Math.max(round.toolRequests.length, round.toolResults.length);
  const items: ToolActionItem[] = [];
  for (let index = 0; index < count; index += 1) {
    const request = round.toolRequests[index] ?? {};
    const result = round.toolResults[index] ?? {};
    const tool = stringValue(result.tool) || stringValue(request.tool) || "unknown";
    const failed = stringValue(result.type).includes("failed") || Boolean(result.error_type || result.error);
    const status = failed ? "failed" : result.type ? "completed" : "pending";
    items.push({
      tool,
      status,
      statusLabel: status === "failed" ? "失败" : status === "completed" ? "已返回" : "等待结果",
      summary: toolActionSummary(tool, request, result),
      arguments: describeToolArguments(request.arguments),
      result: describeToolResult(result),
    });
  }
  return items;
}

function toolActionSummary(tool: string, request: Record<string, unknown>, result: Record<string, unknown>): string {
  if (result.error) return `工具执行失败：${String(result.error)}`;
  if (result.error_type) return `工具参数或执行异常：${String(result.error_type)}`;
  const summary = stringValue(result.summary) || stringValue(request.summary);
  if (summary) return summary;
  if (tool === "execute_code") return "运行模型生成的 Python 分析代码，产出表格、图表或中间结果。";
  if (tool === "save_semantic_finding") return "保存模型识别出的语义发现，供后续项目复用。";
  return "模型调用工具获取更多证据。";
}

function describeToolArguments(value: unknown): string[] {
  const record = recordValue(value);
  if (!record) {
    const text = stringValue(value);
    return text ? [shorten(text, 180)] : [];
  }
  const labels: Record<string, string> = {
    step_name: "步骤",
    step_desc: "目的",
    code_chars: "代码长度",
    question: "问题",
    title: "标题",
    metric_name: "指标",
    finding_type: "发现类型",
  };
  return Object.entries(record)
    .filter(([, item]) => isMeaningful(item))
    .slice(0, 6)
    .map(([key, item]) => `${labels[key] ?? key}：${compactValue(item)}`);
}

function describeToolResult(value: Record<string, unknown>): string | undefined {
  const result = recordValue(value.result);
  if (result) {
    const pieces = [];
    const returncode = result.returncode ?? value.returncode;
    if (returncode != null) pieces.push(`返回码 ${String(returncode)}`);
    const tableCount = result.table_count ?? result.tables_count ?? result.tables;
    const chartCount = result.chart_count ?? result.charts_count ?? result.charts;
    if (tableCount != null) pieces.push(`${countLike(tableCount)} 个表格`);
    if (chartCount != null) pieces.push(`${countLike(chartCount)} 个图表`);
    if (result.output_summary) pieces.push(shorten(String(result.output_summary), 120));
    if (pieces.length) return pieces.join(" · ");
  }
  if (value.result != null) return shorten(compactValue(value.result), 180);
  if (value.summary) return shorten(String(value.summary), 180);
  return undefined;
}

function toolDisplayName(name: string) {
  const labels: Record<string, string> = {
    execute_code: "执行代码",
    save_semantic_finding: "保存语义发现",
    read_preflight: "读取项目上下文",
    list_skills: "列出可用技能",
    load_skill: "加载技能说明",
    run_preflight: "运行前检查",
    profile_dataset: "数据画像",
  };
  return labels[name] ?? (name || "未知工具");
}

function roleLabel(role?: string) {
  const labels: Record<string, string> = {
    system: "系统规则",
    user: "用户/上下文",
    assistant: "模型上一轮",
    tool: "工具结果",
  };
  return labels[role ?? ""] ?? role ?? "未知角色";
}

function compactValue(value: unknown): string {
  if (value == null) return "—";
  if (typeof value === "string") return shorten(value, 180);
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) return `${value.length} 项${value.length ? `：${value.slice(0, 3).map(compactValue).join("、")}` : ""}`;
  const record = recordValue(value);
  if (record) {
    return Object.entries(record).slice(0, 4).map(([key, item]) => `${key}=${compactValue(item)}`).join("；");
  }
  return shorten(String(value), 180);
}

function countLike(value: unknown): string {
  if (Array.isArray(value)) return String(value.length);
  const numeric = numberValue(value);
  return numeric != null ? String(numeric) : compactValue(value);
}

function shorten(value: string, limit: number) {
  return value.length > limit ? `${value.slice(0, limit)}...` : value;
}

function isMeaningful(value: unknown) {
  if (value == null || value === "") return false;
  if (Array.isArray(value)) return value.length > 0;
  const record = recordValue(value);
  if (record) return Object.keys(record).length > 0;
  return true;
}

function eventTypeLabel(type: string) {
  const labels: Record<string, string> = {
    run: "任务",
    workflow_step: "流程步骤",
    tool_call: "工具调用",
    artifact: "产物",
    source: "来源",
    evidence: "证据",
    candidate_angle: "候选分析角度",
    validation_summary: "校验汇总",
    validation_gate: "校验门",
    llm_request_started: "LLM 请求",
    llm_request_completed: "LLM 响应",
    llm_request_failed: "LLM 失败",
    planner_tool_requested: "工具请求",
    planner_tool_completed: "工具结果",
    feedback_evaluated: "质量反馈",
    planner_finalization_forced: "强制收口",
    planner_finalized: "报告收口",
    code_generated: "生成代码",
    code_execution_started: "执行代码",
    code_execution_completed: "执行结果",
  };
  return labels[type] ?? type;
}
