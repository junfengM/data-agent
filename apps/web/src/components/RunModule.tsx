import React from "react";
import { Bot, CheckCircle2, ChevronDown, Code2, FileText, Play, Square, UserRound, Wrench } from "lucide-react";
import type { AnalysisProject, Artifact, Dataset, ModelConfig, ProjectContext, RunResponse, SemanticLayerMeta, Skill } from "../types";
import { EmptyState } from "../shared";
import "../analysis-chat.css";

export type RunStreamEvent = {
  kind?: "event" | "result" | "error";
  type?: string;
  summary?: string;
  data?: Record<string, unknown>;
};

type Props = {
  contexts: ProjectContext[];
  createRun: () => Promise<void>;
  onCancel?: () => Promise<void> | void;
  onNotify?: (message: string, kind?: "error" | "success") => void;
  datasets: Dataset[];
  generatedCodeExecution: string;
  isRunning: boolean;
  models: ModelConfig[];
  projects: AnalysisProject[];
  question: string;
  run: RunResponse | null;
  runEvents: RunStreamEvent[];
  selectedContextIds: string[];
  selectedDatasetIds: string[];
  selectedModelId: string;
  selectedProject?: AnalysisProject;
  selectedProjectId: string;
  selectedSkill: string;
  semanticLayer: SemanticLayerMeta | null;
  setQuestion: React.Dispatch<React.SetStateAction<string>>;
  setSelectedModelId: React.Dispatch<React.SetStateAction<string>>;
  setSelectedProjectId: React.Dispatch<React.SetStateAction<string>>;
  setSelectedSkill: React.Dispatch<React.SetStateAction<string>>;
  skills: Skill[];
  toggleContext: (contextId: string) => void;
  toggleDataset: (datasetId: string) => void;
};

export type TimelineMessage = {
  role: "user" | "assistant" | "system" | "tool" | "code" | "report";
  title: string;
  body: string;
  status?: string;
  compact?: boolean;
  preview?: string;
  mergeKey?: string;
};

type RunInputSection =
  | "project"
  | "contexts"
  | "datasets"
  | "semantic"
  | "skill"
  | "model"
  | null;

const summaryButtonStyle: React.CSSProperties = {
  background: "transparent",
  border: 0,
  color: "inherit",
  cursor: "pointer",
  display: "grid",
  gap: 6,
  padding: 0,
  textAlign: "left",
  width: "100%",
};

const inertSummaryStyle: React.CSSProperties = {
  ...summaryButtonStyle,
  cursor: "default",
};

const previewStyle: React.CSSProperties = {
  color: "#64748b",
  fontSize: 12,
  lineHeight: 1.55,
  margin: 0,
  overflow: "hidden",
  textOverflow: "ellipsis",
  whiteSpace: "pre-wrap",
};

const detailPanelStyle: React.CSSProperties = {
  borderTop: "1px solid #e2e8f0",
  marginTop: 10,
  maxHeight: 340,
  overflow: "auto",
  paddingTop: 10,
};

const detailTextStyle: React.CSSProperties = {
  lineHeight: 1.65,
  margin: 0,
  whiteSpace: "pre-wrap",
};

const titleMetaStyle: React.CSSProperties = {
  alignItems: "center",
  display: "inline-flex",
  flexWrap: "wrap",
  gap: 8,
  justifyContent: "flex-end",
};

export default function RunModule(props: Props) {
  const [openSection, setOpenSection] = React.useState<RunInputSection>(null);
  const chatListRef = React.useRef<HTMLDivElement | null>(null);
  const composerCardRef = React.useRef<HTMLDivElement | null>(null);
  const selectedContexts = props.contexts.filter((context) =>
    props.selectedContextIds.includes(context.id)
  );
  const selectedDatasets = props.datasets.filter((dataset) =>
    props.selectedDatasetIds.includes(dataset.id)
  );
  const selectedSkillName = props.skills.find((skill) => skill.id === props.selectedSkill)?.name ?? "自动路由";
  const selectedModel = props.models.find((model) => model.id === props.selectedModelId);
  const isLocalExecutionEnabled = ["local", "local-dev"].includes(props.generatedCodeExecution);
  const canRun = (() => {
    if (!props.selectedProject) return false;
    if (selectedDatasets.length === 0) return false;
    if (!selectedModel) return false;
    return isLocalExecutionEnabled;
  })();
  const runButtonLabel = (() => {
    if (props.isRunning) return "运行中";
    if (canRun) return "开始分析";
    return "待配置";
  })();
  const runDisabledReason = (() => {
    if (props.isRunning) return "";
    if (!props.selectedProject) return "需要先选择或创建一个分析项目";
    if (selectedDatasets.length === 0) return "需要先上传并选择数据集";
    if (!selectedModel) return "需要先在系统设置中配置模型";
    if (!isLocalExecutionEnabled) return "需要在 server/.env 开启本地代码执行（local-dev）";
    return "";
  })();
  const timelineMessages = buildTimelineMessages({
    isRunning: props.isRunning,
    question: props.question,
    run: props.run,
    runEvents: props.runEvents,
    selectedContexts,
    selectedDatasets,
    selectedModel,
    selectedProject: props.selectedProject,
    selectedSkillId: props.selectedSkill,
    selectedSkillName,
    semanticLayer: props.semanticLayer,
  });
  const hasRunActivity = props.isRunning || props.runEvents.length > 0 || Boolean(props.run);

  React.useEffect(() => {
    if (!hasRunActivity) return;
    const node = chatListRef.current;
    if (!node) return;
    node.scrollTo({ top: node.scrollHeight, behavior: "smooth" });
  }, [hasRunActivity, timelineMessages.length, props.runEvents.length, props.isRunning]);

  React.useEffect(() => {
    if (!openSection) return;

    function handlePointerDown(event: PointerEvent) {
      const target = event.target as Node | null;
      if (target && composerCardRef.current?.contains(target)) return;
      setOpenSection(null);
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setOpenSection(null);
    }

    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [openSection]);

  function toggleSection(section: RunInputSection) {
    setOpenSection((current) => (current === section ? null : section));
  }

  function handleRun() {
    if (!props.selectedProject) {
      props.onNotify?.("请先选择本次运行的分析项目。", "error");
      setOpenSection("project");
      return;
    }
    if (selectedDatasets.length === 0) {
      props.onNotify?.("请先选择本次运行要使用的数据集。", "error");
      setOpenSection("datasets");
      return;
    }
    if (!selectedModel) {
      props.onNotify?.("请先选择本次运行使用的模型。", "error");
      setOpenSection("model");
      return;
    }
    if (!selectedModel.api_key_configured) {
      const confirmed = window.confirm(
        `当前模型 ${selectedModel.id} 的 API Key 未配置。\n\n` +
          `请在 server/.env 中配置 ${selectedModel.api_key_env} 后重启服务。\n\n` +
          "仍要继续运行并让后端返回具体错误吗？"
      );
      if (!confirmed) return;
    }
    if (isLocalExecutionEnabled) {
      const confirmed = window.confirm(
        "本地代码执行已启用\n\n" +
          "运行将执行 LLM 生成的 Python 代码，该代码可以访问本地文件系统。\n\n" +
          "仅在信任分析问题和数据集的情况下继续。\n\n" +
          "点击「确定」继续运行，或「取消」中止。"
      );
      if (!confirmed) return;
    }
    setOpenSection(null);
    props.createRun();
  }

  return (
    <div className={`run-workspace ${hasRunActivity ? "active-run" : "idle-run"}`}>
      <section className="run-hero-panel">
        <div className="run-hero-copy">
          <span className="run-eyebrow">Data Analysis Agent</span>
          <h2>一起探索数据</h2>
        </div>

        <h3 className="run-composer-heading">想分析什么数据？</h3>

        <div className="run-composer-card" ref={composerCardRef}>
          <textarea
            aria-label="分析提示词"
            className="run-composer-input"
            onChange={(event) => props.setQuestion(event.target.value)}
            placeholder="输入你想让数据分析 Agent 回答的问题……"
            value={props.question}
          />

          <div className="run-composer-toolbar">
            <RunMenuButton
              isActive={openSection === "project"}
              isReady={Boolean(props.selectedProject)}
              label="项目"
              onClick={() => toggleSection("project")}
              summary={props.selectedProject?.name ?? "选择项目"}
            />
            <RunMenuButton
              isActive={openSection === "datasets"}
              isReady={selectedDatasets.length > 0}
              label="数据"
              onClick={() => toggleSection("datasets")}
              summary={selectedDatasets.length ? `${selectedDatasets.length} 个数据集` : "选择数据"}
            />
            <RunMenuButton
              isActive={openSection === "contexts"}
              isReady={selectedContexts.length > 0}
              label="上下文"
              onClick={() => toggleSection("contexts")}
              summary={selectedContexts.length ? `${selectedContexts.length} 条上下文` : "可选"}
            />
            <RunMenuButton
              isActive={openSection === "semantic"}
              isReady={Boolean(props.semanticLayer)}
              label="语义层"
              onClick={() => toggleSection("semantic")}
              summary={props.semanticLayer?.name || "自动推导"}
            />
            <RunMenuButton
              isActive={openSection === "skill"}
              isReady={Boolean(props.selectedSkill)}
              label="技能"
              onClick={() => toggleSection("skill")}
              summary={selectedSkillName}
            />
            <RunMenuButton
              isActive={openSection === "model"}
              isReady={Boolean(selectedModel?.api_key_configured)}
              label="模型"
              onClick={() => toggleSection("model")}
              summary={selectedModel?.id ?? "选择模型"}
            />
            <button
              className="run-send-button"
              data-testid="run-workflow"
              disabled={props.isRunning || !canRun}
              onClick={handleRun}
              title={props.isRunning || canRun ? undefined : runDisabledReason}
              type="button"
            >
              <Play size={16} />
              {runButtonLabel}
            </button>
            {props.isRunning && props.onCancel && (
              <button
                className="run-send-button run-cancel-button"
                data-testid="cancel-run"
                onClick={() => void props.onCancel?.()}
                type="button"
              >
                <Square size={16} />
                取消
              </button>
            )}
          </div>
          {!props.isRunning && !canRun && runDisabledReason && (
            <p className="run-hint" data-testid="run-hint">
              还差一步：{runDisabledReason}
            </p>
          )}

          {openSection && (
            <div className="run-menu-popover">
              {openSection === "project" && (
                <RunMenuPanel title="选择分析项目" subtitle="数据、上下文和语义层会绑定到当前项目。">
                  <div className="run-selector-list">
                    {props.projects.length ? (
                      props.projects.map((project) => (
                        <button
                          className={`run-selector-option ${props.selectedProjectId === project.id ? "selected" : ""}`}
                          key={project.id}
                          onClick={() => {
                            props.setSelectedProjectId(project.id);
                            setOpenSection("datasets");
                          }}
                          type="button"
                        >
                          <span>{project.name}</span>
                          <small>{project.description || project.status}</small>
                        </button>
                      ))
                    ) : (
                      <EmptyState text="还没有分析项目。请先到「项目」页面创建。" />
                    )}
                  </div>
                </RunMenuPanel>
              )}

              {openSection === "datasets" && (
                <RunMenuPanel title="选择本次运行数据" subtitle="Agent 会基于勾选的数据集做画像、规划、执行和报告输出。">
                  <div className="run-selector-list compact-list">
                    {props.selectedProjectId ? (
                      props.datasets.length ? (
                        props.datasets.map((dataset) => (
                          <label className="dataset-row light" key={dataset.id} title={dataset.path}>
                            <input
                              checked={props.selectedDatasetIds.includes(dataset.id)}
                              onChange={() => props.toggleDataset(dataset.id)}
                              type="checkbox"
                            />
                            <span>{dataset.filename}</span>
                            <small>{dataset.created_at ?? "本地文件"}</small>
                          </label>
                        ))
                      ) : (
                      <EmptyState text="当前项目还没有可用数据集。" hint="上传 CSV/XLSX 文件后即可开始分析。" />
                      )
                    ) : (
                      <EmptyState text="请先选择分析项目。" />
                    )}
                  </div>
                </RunMenuPanel>
              )}

              {openSection === "contexts" && (
                <RunMenuPanel title="选择项目上下文" subtitle="上下文会作为本次分析的业务背景和约束。">
                  <div className="run-selector-list compact-list">
                    {props.selectedProjectId ? (
                      props.contexts.length ? (
                        props.contexts.map((context) => (
                          <label className="dataset-row light" key={context.id} title={context.body}>
                            <input
                              checked={props.selectedContextIds.includes(context.id)}
                              onChange={() => props.toggleContext(context.id)}
                              type="checkbox"
                            />
                            <span>{context.title}</span>
                            <small>{context.kind}</small>
                          </label>
                        ))
                      ) : (
                        <EmptyState text="当前项目还没有上下文；可以继续运行，也可以先到「上下文」页面配置。" />
                      )
                    ) : (
                      <EmptyState text="请先选择分析项目。" />
                    )}
                  </div>
                </RunMenuPanel>
              )}

              {openSection === "semantic" && (
                <RunMenuPanel title="语义层" subtitle="语义层决定 Agent 如何理解指标、维度和业务口径。">
                  <div className="run-selector-note">
                    <strong>{props.semanticLayer?.name || "未配置语义层"}</strong>
                    <span>
                      {props.semanticLayer
                        ? "本次运行会使用当前项目的激活语义层。"
                        : "没有语义层时，会根据数据画像临时推导分析含义。"}
                    </span>
                  </div>
                </RunMenuPanel>
              )}

              {openSection === "skill" && (
                <RunMenuPanel title="选择入口技能" subtitle="通常使用自动路由即可；也可以固定一个分析入口。">
                  <div className="run-selector-list skill-selector-list">
                    <button
                      className={`run-selector-option ${!props.selectedSkill ? "selected" : ""}`}
                      onClick={() => {
                        props.setSelectedSkill("");
                        setOpenSection(null);
                      }}
                      type="button"
                    >
                      <span>自动路由</span>
                      <small>由系统根据问题自动选择入口技能</small>
                    </button>
                    {props.skills.map((skill) => (
                      <button
                        className={`run-selector-option skill-option ${props.selectedSkill === skill.id ? "selected" : ""}`}
                        key={skill.id}
                        onClick={() => {
                          props.setSelectedSkill(skill.id);
                          setOpenSection(null);
                        }}
                        type="button"
                        title={`${skill.name}\n${skill.id}\n${skill.trigger || ""}`}
                      >
                        <span>{skill.name}</span>
                        <small>{skill.id}</small>
                        {skill.trigger && <small className="skill-trigger">触发：{skill.trigger}</small>}
                      </button>
                    ))}
                  </div>
                </RunMenuPanel>
              )}

              {openSection === "model" && (
                <RunMenuPanel title="选择本次模型" subtitle="本次运行会把该模型配置 ID 发送给后端；DeepSeek 使用 openai_compatible 接入。">
                  <div className="run-selector-list skill-selector-list">
                    {props.models.length ? (
                      props.models.map((model) => (
                        <button
                          className={`run-selector-option skill-option ${props.selectedModelId === model.id ? "selected" : ""}`}
                          key={model.id}
                          onClick={() => {
                            props.setSelectedModelId(model.id);
                            setOpenSection(null);
                          }}
                          type="button"
                          title={`${model.id}\n${model.provider}\n${model.base_url || ""}\n${model.model}`}
                        >
                          <span>{model.id}</span>
                          <small>{model.provider} · {model.model}</small>
                          <small>{model.base_url || "默认服务地址"}</small>
                          <small className="skill-trigger">
                            {model.api_key_configured ? "API Key 已配置" : `缺少 ${model.api_key_env}`}
                          </small>
                        </button>
                      ))
                    ) : (
                      <EmptyState text="还没有模型配置。请先在 config/models.yaml 中配置 DeepSeek。" />
                    )}
                  </div>
                </RunMenuPanel>
              )}

            </div>
          )}
        </div>

        {!isLocalExecutionEnabled && (
          <p className="run-disabled-note">
            在 server/.env 中设置 DATA_AGENT_GENERATED_CODE_EXECUTION=local-dev 以启用本地开发执行。
          </p>
        )}
      </section>

      {hasRunActivity && (
        <section className="analysis-chat-panel run-conversation-panel">
          <div className="run-section-heading">
            <span>Analysis stream</span>
            <h3>分析过程</h3>
          </div>
          <div className="analysis-chat-list" ref={chatListRef}>
            {timelineMessages.map((message, index) => (
              <AnalysisMessage message={message} key={`${message.role}-${index}-${message.title}`} />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

function RunMenuButton(props: {
  isActive: boolean;
  isReady: boolean;
  label: string;
  onClick: () => void;
  summary: string;
}) {
  return (
    <button
      className={`run-menu-button ${props.isActive ? "active" : ""} ${props.isReady ? "ready" : ""}`}
      onClick={props.onClick}
      type="button"
    >
      <span>{props.label}</span>
      <small>{props.summary}</small>
      <ChevronDown size={14} />
    </button>
  );
}

function RunMenuPanel(props: { children: React.ReactNode; subtitle: string; title: string }) {
  return (
    <section className="run-menu-panel">
      <header>
        <strong>{props.title}</strong>
        <span>{props.subtitle}</span>
      </header>
      {props.children}
    </section>
  );
}

function AnalysisMessage({ message }: { message: TimelineMessage }) {
  const [isExpanded, setIsExpanded] = React.useState(false);
  const Icon = iconForRole(message.role);
  const hasDetails = Boolean(message.body.trim());
  const preview = getMessagePreview(message);
  const detailId = React.useId();
  const canToggle = hasDetails && !message.compact;

  return (
    <article className={`analysis-message ${message.role} ${message.compact ? "compact" : ""}`}>
      <div className="analysis-message-icon">
        <Icon size={16} />
      </div>
      <div className="analysis-message-body">
        <button
          aria-controls={canToggle ? detailId : undefined}
          aria-expanded={canToggle ? isExpanded : undefined}
          disabled={!canToggle}
          onClick={() => canToggle && setIsExpanded((current) => !current)}
          style={canToggle ? summaryButtonStyle : inertSummaryStyle}
          type="button"
        >
          <div className="analysis-message-title">
            <strong>{message.title}</strong>
            <span style={titleMetaStyle}>
              {message.status && <span>{message.status}</span>}
              {canToggle && <span>{isExpanded ? "收起详情" : "查看详情"}</span>}
            </span>
          </div>
          {preview ? <p style={previewStyle}>{preview}</p> : null}
        </button>

        {canToggle && isExpanded && (
          <div id={detailId} style={detailPanelStyle}>
            {message.role === "code" ? (
              <pre className="analysis-code-block"><code>{message.body}</code></pre>
            ) : (
              <p style={detailTextStyle}>{message.body}</p>
            )}
          </div>
        )}
      </div>
    </article>
  );
}

function iconForRole(role: TimelineMessage["role"]) {
  if (role === "user") return UserRound;
  if (role === "tool") return Wrench;
  if (role === "code") return Code2;
  if (role === "report") return FileText;
  if (role === "system") return CheckCircle2;
  return Bot;
}

type TimelineInput = {
  isRunning: boolean;
  question: string;
  run: RunResponse | null;
  runEvents: RunStreamEvent[];
  selectedContexts: ProjectContext[];
  selectedDatasets: Dataset[];
  selectedModel?: ModelConfig;
  selectedProject?: AnalysisProject;
  selectedSkillId: string;
  selectedSkillName: string;
  semanticLayer: SemanticLayerMeta | null;
};

function buildTimelineMessages(input: TimelineInput): TimelineMessage[] {
  if (input.isRunning || input.runEvents.length) {
    return buildStreamingMessages(input);
  }
  if (!input.run) {
    return [];
  }
  return [
    ...buildRunInputMessages(input),
    ...buildCompletedMessages(input.run).slice(1),
  ];
}

function streamEventMergeKey(event: RunStreamEvent) {
  const data = event.data ?? {};
  const iteration = String(data.iteration ?? "");
  const tool = String(data.tool ?? "");
  const stepName = String(data.step_name ?? "");
  const toolCallId = String(data.tool_call_id ?? "");

  switch (event.type) {
    case "planner_tool_requested":
    case "planner_tool_completed":
    case "planner_tool_failed":
      return toolCallId
        ? `planner_tool:${toolCallId}`
        : `planner_tool:${iteration}:${tool}`;

    case "llm_request_started":
    case "llm_request_completed":
    case "llm_request_failed":
      return `llm_request:${iteration}`;

    case "dataset_profile_started":
    case "dataset_profile_completed":
      return "dataset_profile";

    case "code_execution_started":
    case "code_execution_completed":
      return `code_execution:${stepName}`;

    case "report_generation_started":
    case "report_generated":
      return "report_generation";

    case "validation_started":
    case "validation_completed":
      return "validation";

    default:
      return undefined;
  }
}

function mergeOrAppendMessage(messages: TimelineMessage[], message: TimelineMessage) {
  if (!message.mergeKey) {
    messages.push(message);
    return;
  }

  const existingIndex = messages.findIndex((item) => item.mergeKey === message.mergeKey);
  if (existingIndex >= 0) {
    const previous = messages[existingIndex];
    messages[existingIndex] = {
      ...previous,
      ...message,
      body: [
        previous.body,
        message.body && previous.body !== message.body ? `\n\n${message.body}` : "",
      ].filter(Boolean).join(""),
    };
    return;
  }

  messages.push(message);
}

function buildStreamingMessages(input: TimelineInput): TimelineMessage[] {
  const messages: TimelineMessage[] = buildRunInputMessages(input);
  let lastMeaningfulEvent: RunStreamEvent | undefined;

  for (const event of input.runEvents) {
    if (event.kind !== "event") continue;
    if (event.type === "heartbeat") continue;

    lastMeaningfulEvent = event;
    mergeOrAppendMessage(messages, messageFromStreamEvent(event));
  }

  if (input.run && !input.runEvents.some((event) => event.type === "run_completed")) {
    messages.push({
      role: "system",
      title: "分析完成",
      status: translateStatus(input.run.status),
      body: "本次分析已结束，可到「报告产物」查看报告、校验结果和导出入口。",
    });
  }

  if (input.isRunning && !input.run && lastMeaningfulEvent?.type !== "run_completed") {
    messages.push(buildRunningPlaceholder());
  }

  return messages;
}

function buildRunningPlaceholder(): TimelineMessage {
  return {
    role: "system",
    title: "正在运行中",
    status: "等待流式输出",
    body: "",
    compact: true,
  };
}

function buildRunInputMessages(input: TimelineInput): TimelineMessage[] {
  const contextSummary = input.selectedContexts.length
    ? input.selectedContexts
        .map((context, index) => `${index + 1}. ${context.title} (${context.kind})\n${context.body}`)
        .join("\n\n")
    : "本次运行未选择项目上下文。";

  const datasetSummary = input.selectedDatasets.length
    ? input.selectedDatasets.map((dataset) => `- ${dataset.filename}`).join("\n")
    : "本次运行未选择数据集。";

  return [
    {
      role: "user",
      title: "用户分析提示词",
      status: "已接收",
      preview: "",
      body: input.question,
    },
    {
      role: "system",
      title: "运行输入快照",
      status: "已选择",
      preview: [
        input.selectedProject?.name ? `项目：${input.selectedProject.name}` : "项目未选择",
        input.selectedDatasets.length ? `数据集：${input.selectedDatasets.length} 个` : "未选数据集",
        input.selectedModel ? `模型：${input.selectedModel.id}` : "未选模型",
      ].join(" · "),
      body: [
        `项目：${input.selectedProject?.name ?? "未选择项目"}`,
        `入口技能：${input.selectedSkillId ? `${input.selectedSkillName} (${input.selectedSkillId})` : "自动路由"}`,
        `本次模型：${input.selectedModel ? `${input.selectedModel.id} (${input.selectedModel.provider} / ${input.selectedModel.model})` : "未选择"}`,
        `语义层：${input.semanticLayer?.name ?? "未配置；运行时会基于数据画像临时推导"}`,
        `数据集：\n${datasetSummary}`,
      ].join("\n"),
    },
    {
      role: "system",
      title: "本次运行上下文",
      status: input.selectedContexts.length ? `${input.selectedContexts.length} 条` : "未选择",
      preview: input.selectedContexts.length
        ? `已加载 ${input.selectedContexts.length} 条项目上下文。`
        : "本次未选择项目上下文。",
      body: contextSummary,
    },
  ];
}

function humanToolName(tool?: unknown) {
  const name = String(tool || "");
  const mapping: Record<string, string> = {
    read_preflight: "读取项目资料和语义层",
    list_skills: "查看可用分析方法",
    load_skill: "加载分析方法",
    execute_code: "执行数据计算",
    evaluate_attempt: "检查分析质量",
    save_semantic_finding: "保存可复用指标定义",
  };
  return mapping[name] ?? (name || "工具");
}

function summarizePlannerToolResult(tool: unknown, result: unknown, fallback: string) {
  const toolName = String(tool || "");
  const resultText = typeof result === "string" ? result : "";

  if (toolName === "execute_code") {
    return resultText || "数据计算已完成，系统已收集输出表格、图表或运行结果。";
  }
  if (toolName === "evaluate_attempt") {
    return "已检查当前分析草稿的证据覆盖、报告质量和是否需要修复。";
  }
  if (toolName === "read_preflight") {
    return "已读取项目上下文、语义层、数据可用性和运行前检查信息。";
  }
  if (toolName === "list_skills") {
    return "已读取当前可用的分析方法，用于选择合适的分析入口。";
  }
  if (toolName === "load_skill") {
    return "已加载本次分析需要使用的分析方法和输出要求。";
  }
  return fallback || "这一步已完成。";
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function numberValue(value: unknown): number | undefined {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return undefined;
}

function countLabel(value: number | undefined, unit: string) {
  return `${Math.max(0, Math.trunc(value ?? 0))} 个${unit}`;
}

function outputCountParts(data: Record<string, unknown>) {
  const tableCount = numberValue(data.table_count ?? data.tables_count) ?? (
    Array.isArray(data.tables) ? data.tables.length : undefined
  );
  const chartCount = numberValue(data.chart_count ?? data.charts_count) ?? (
    Array.isArray(data.charts) ? data.charts.length : undefined
  );
  return [
    tableCount !== undefined ? countLabel(tableCount, "表格") : "",
    chartCount !== undefined ? countLabel(chartCount, "图表") : "",
  ].filter(Boolean);
}

function outputCountSentence(data: Record<string, unknown>) {
  const parts = outputCountParts(data);
  return parts.length ? parts.join("、") : "未记录表格或图表";
}

function validationPreview(data: Record<string, unknown>, summary: string) {
  const parsedFromSummary = summary.match(/(\d+)\s*\/\s*(\d+)/);
  const passCount = numberValue(data.pass_count ?? data.passed_count) ?? (
    parsedFromSummary ? Number(parsedFromSummary[1]) : undefined
  );
  const gateCount = numberValue(data.gate_count ?? data.total_count ?? data.validation_count) ?? (
    parsedFromSummary ? Number(parsedFromSummary[2]) : undefined
  );
  const failCount = numberValue(data.fail_count ?? data.failure_count);
  const warningCount = numberValue(data.warning_count ?? data.warn_count);
  const parts = [
    passCount !== undefined && gateCount !== undefined ? `${passCount}/${gateCount} 通过` : "",
    failCount !== undefined ? `${failCount} 失败` : "",
    warningCount !== undefined ? `${warningCount} 警告` : "",
  ].filter(Boolean);
  return parts.join(" · ");
}

function formatTokenUsage(usage: unknown) {
  const record = asRecord(usage);
  const total = numberValue(record.total_tokens);
  const prompt = numberValue(record.prompt_tokens);
  const completion = numberValue(record.completion_tokens);
  if (total === undefined) return "";
  const parts = [`Token：${total}`];
  const breakdown = [
    prompt !== undefined ? `输入 ${prompt}` : "",
    completion !== undefined ? `输出 ${completion}` : "",
  ].filter(Boolean);
  return breakdown.length ? `${parts[0]}（${breakdown.join("，")}）` : parts[0];
}

function summarizeToolArguments(value: unknown, toolNames: unknown[] = []) {
  if (!Array.isArray(value) || !value.length) return "";
  const summaries = value.slice(0, 3).map((item, index) => {
    const record = asRecord(item);
    const args = asRecord(record.arguments);
    const toolName = humanToolName(record.tool ?? record.name ?? toolNames[index]);
    const stepName = String(record.step_name ?? args.step_name ?? args.name ?? args.title ?? "").trim();
    const codeChars = numberValue(record.code_chars);
    const detail = [
      stepName,
      codeChars !== undefined ? `${codeChars} 字符代码` : "",
    ].filter(Boolean).join(" · ");
    return `${index + 1}. ${toolName}${detail ? `：${detail}` : ""}`;
  });
  const suffix = value.length > summaries.length ? `\n其余 ${value.length - summaries.length} 组参数已省略。` : "";
  return `${summaries.join("\n")}${suffix}`;
}

function previewText(value: unknown) {
  const record = asRecord(value);
  const head = String(record.head ?? "");
  const tail = String(record.tail ?? "");
  const truncated = Boolean(record.truncated);
  if (!truncated || !tail) return head;
  return `${head}\n...\n${tail}`;
}

function formatPromptSnapshot(value: unknown) {
  const snapshot = asRecord(value);
  const messages = Array.isArray(snapshot.messages) ? snapshot.messages : [];
  if (!messages.length) return "";
  const header = [
    `Prompt 快照：${String(snapshot.included_message_count ?? messages.length)}/${String(snapshot.message_count ?? messages.length)} 条消息`,
    `总内容字符：${String(snapshot.total_content_chars ?? "未知")}`,
    numberValue(snapshot.omitted_message_count) ? `中间省略：${String(snapshot.omitted_message_count)} 条消息` : "",
  ].filter(Boolean).join(" · ");
  const lines = messages.map((item) => {
    const message = asRecord(item);
    const content = previewText(message.content_preview);
    const toolCalls = Array.isArray(message.tool_calls) ? message.tool_calls : [];
    const toolCallText = toolCalls.map((toolCall, index) => {
      const call = asRecord(toolCall);
      const args = previewText(call.arguments_preview);
      return [
        `  tool_call ${index + 1}：${String(call.name || "工具")}`,
        args ? indentText(args, "    ") : "",
      ].filter(Boolean).join("\n");
    }).filter(Boolean).join("\n");
    return [
      `#${String(message.index ?? "?")} ${String(message.role || "unknown")} · ${String(message.content_chars ?? 0)} 字符`,
      content ? indentText(content, "  ") : "  （无文本内容）",
      toolCallText,
    ].filter(Boolean).join("\n");
  });
  return [header, ...lines].join("\n\n");
}

function indentText(text: string, prefix: string) {
  return text.split("\n").map((line) => `${prefix}${line}`).join("\n");
}

export function messageFromStreamEvent(event: RunStreamEvent): TimelineMessage {
  const data = event.data ?? {};
  const summary = event.summary || "";
  switch (event.type) {
    case "run_started":
      return {
        role: "system",
        title: "任务已启动",
        status: "实时",
        body: data.model_config_id
          ? `本次运行已开始，使用模型 ${String(data.model_config_id)}。\n\n${summary}`
          : `本次运行已开始。${summary}`,
      };
    case "context_loaded":
      return {
        role: "system",
        title: "准备上下文",
        status: "完成",
        body: summary || "已加载项目上下文、数据画像和语义层信息，为分析做准备。",
      };
    case "dataset_profile_started":
      return {
        role: "tool",
        title: "读取并理解数据",
        status: "进行中",
        preview: "正在读取数据。",
        mergeKey: streamEventMergeKey(event),
        body: summary || "开始：正在读取所选数据集，识别字段类型、缺失情况和可分析指标。",
      };
    case "dataset_profile_completed":
      return {
        role: "tool",
        title: "读取并理解数据",
        status: "完成",
        preview: "数据理解完成。",
        mergeKey: streamEventMergeKey(event),
        body: summary || "完成：系统已读取所选数据集，识别字段类型、缺失情况、时间字段和可用于分析的指标。后续分析会基于这些数据画像生成代码和报告。",
      };
    case "preflight_completed":
      return {
        role: "system",
        title: "检查运行环境",
        status: "完成",
        body: summary || "已检查项目、数据、上下文和运行环境，确认可以开始分析。",
      };
    case "planning_started":
      return {
        role: "assistant",
        title: "制定分析方案",
        status: "进行中",
        body: summary
          ? `${summary}\n\n模型正在根据问题、数据画像和上下文，规划需要执行的分析步骤。`
          : "模型正在根据问题、数据画像和上下文，规划需要执行的分析步骤。这里展示中文可解释摘要，不展示模型内部隐藏思维链。",
      };
    case "planning_completed": {
      const selectedSkills = Array.isArray(data.selected_skills) ? data.selected_skills.map(String) : [];
      const skillLine = selectedSkills.length ? `\n\n本次选用的分析方法：${selectedSkills.join("、")}` : "";
      const caveats = Array.isArray(data.caveats) && data.caveats.length
        ? `\n\n注意事项：\n${data.caveats.map(String).map((item) => `- ${item}`).join("\n")}`
        : "";
      return {
        role: "assistant",
        title: "分析方案已生成",
        status: "完成",
        body: `${String(data.plan_summary || summary || "分析方案已生成。")}${skillLine}${caveats}`,
      };
    }
    case "code_generated":
      return {
        role: "code",
        title: `生成执行代码：${String(data.step_name || "分析步骤")}`,
        status: "已生成",
        body: String(data.code || summary || "代码已生成，系统接下来会执行这段代码进行数据计算。"),
      };
    case "code_execution_started": {
      const stepName = String(data.step_name || "分析步骤");
      return {
        role: "tool",
        title: `执行数据计算：${stepName}`,
        status: "进行中",
        preview: `正在执行数据计算。`,
        mergeKey: streamEventMergeKey(event),
        body: summary || `开始：正在执行生成的 Python 代码，对数据进行 ${stepName}。`,
      };
    }
    case "code_execution_completed": {
      const returncode = Number(data.returncode ?? 0);
      const outputSummary = outputCountSentence(data);
      const stdout = data.stdout ? `\n\n关键输出：\n${truncateText(String(data.stdout), 800)}` : "";
      const stderr = data.stderr ? `\n\n错误信息：\n${truncateText(String(data.stderr), 800)}` : "";
      const stepName = String(data.step_name || "分析步骤");
      return {
        role: "tool",
        title: `执行数据计算：${stepName}`,
        status: returncode === 0 ? "完成" : "失败",
        preview: returncode === 0 ? `完成 · ${outputSummary}` : "失败 · 等待修复或说明限制",
        mergeKey: streamEventMergeKey(event),
        body: returncode === 0
          ? `完成：这一步已完成数据计算。\n产出：${outputSummary}。${stdout}`
          : `完成：这一步执行失败，系统会尝试修复或在报告中说明限制。${stderr}`,
      };
    }
    case "diagnosis_completed": {
      const selectedSkills = Array.isArray(data.selected_skills) ? data.selected_skills.map(String) : [];
      return {
        role: "assistant",
        title: "形成诊断",
        status: "完成",
        body: selectedSkills.length
          ? `${summary || "诊断完成，已形成分析结论。"}\n\n本次使用的分析方法：${selectedSkills.join("、")}`
          : summary || "诊断完成，已基于数据计算结果形成分析结论。",
      };
    }
    case "report_generation_started":
      return {
        role: "report",
        title: "整理报告",
        status: "进行中",
        preview: "正在整理报告。",
        mergeKey: streamEventMergeKey(event),
        body: summary || "开始：正在基于数据计算结果和分析结论，整理结构化报告。",
      };
    case "report_generated":
      return {
        role: "report",
        title: "整理报告",
        status: "完成",
        preview: "报告生成完成。",
        mergeKey: streamEventMergeKey(event),
        body: data.report_preview
          ? `完成：${summary || "报告已生成。"}\n\n${String(data.report_preview)}`
          : summary || "完成：报告已生成，包含分析结论、图表和验证结果。",
      };
    case "validation_started":
      return {
        role: "system",
        title: "校验结果",
        status: "进行中",
        preview: "正在校验报告质量。",
        mergeKey: streamEventMergeKey(event),
        body: summary || "开始：正在校验报告质量，检查证据完整性、数据一致性和输出格式。",
      };
    case "validation_completed":
      {
        const preview = validationPreview(data, summary);
        const passed = Boolean(data.validation_passed);
        return {
          role: "system",
          title: "校验结果",
          status: passed ? "通过" : "需关注",
          preview: preview || (passed ? "校验通过。" : "校验需关注。"),
          mergeKey: streamEventMergeKey(event),
          body: [
            summary,
            passed
              ? "完成：报告已通过质量门禁，证据完整性、数据一致性和输出格式已校验。"
              : "完成：部分质量门禁需关注，请在报告中查看失败项、警告和限制说明。",
          ].filter(Boolean).join("\n"),
        };
      }
    case "run_completed":
      return {
        role: "system",
        title: "运行完成",
        status: String(data.status || "完成"),
        body: summary || "本次分析运行已完成，可到「报告产物」查看完整报告。",
      };
    case "planning_failed":
      return {
        role: "assistant",
        title: "分析方案生成失败",
        status: "fallback",
        body: summary || "生成分析方案时遇到问题，请检查问题描述和所选数据。",
      };
    case "llm_request_started": {
      const iteration = data.iteration ? `第 ${String(data.iteration)} 次` : "本次";
      const tools = Array.isArray(data.available_tools)
        ? data.available_tools.map(humanToolName)
        : [];
      const promptSnapshot = formatPromptSnapshot(data.prompt_snapshot);
      const contextBudget = asRecord(data.context_budget);
      const estimatedContextChars = numberValue(data.estimated_context_chars ?? contextBudget.estimated_context_chars);
      return {
        role: "assistant",
        title: "模型决策记录",
        status: "进行中",
        preview: `${iteration}模型调用开始 · ${String(data.phase || "analysis")} · ${String(data.message_count ?? contextBudget.message_count ?? "未知")} 条消息`,
        mergeKey: streamEventMergeKey(event),
        body: [
          `开始：${iteration}模型调用开始。`,
          "系统会把当前问题、数据画像、项目上下文、语义层和已有工具结果传给模型，让模型判断下一步动作。这里展示本轮请求内容、工具选择和可观测决策记录，不展示模型内部隐藏思维链。",
          `消息数量：${String(data.message_count ?? "未知")}`,
          `提示词字符数：${String(data.prompt_chars ?? "未知")}`,
          estimatedContextChars !== undefined ? `估算上下文字符数：${estimatedContextChars}` : "",
          `已完成数据计算次数：${String(data.execution_count ?? 0)}`,
          `修复轮次：${String(data.feedback_rounds ?? 0)}`,
          `是否进入最终报告收尾：${data.force_finalize ? "是" : "否"}`,
          tools.length ? `本轮可用工具：${tools.join("、")}` : "本轮没有开放工具，模型只能整理最终输出。",
          promptSnapshot ? `\n${promptSnapshot}` : "",
        ].join("\n"),
      };
    }
    case "llm_request_completed": {
      const requestedToolNames = Array.isArray(data.requested_tool_names)
        ? data.requested_tool_names
        : (Array.isArray(data.requested_tools) ? data.requested_tools : []);
      const tools = requestedToolNames.map(humanToolName);
      const toolArguments = summarizeToolArguments(data.tool_arguments, requestedToolNames);
      const usage = formatTokenUsage(data.usage);
      const duration = numberValue(data.duration_ms ?? data.latency_ms);
      return {
        role: "assistant",
        title: "模型决策记录",
        status: "完成",
        preview: tools.length
          ? `下一步：${tools.join("、")}`
          : "模型返回了分析内容。",
        mergeKey: streamEventMergeKey(event),
        body: [
          tools.length
            ? `本轮意图：调用工具继续推进分析。\n下一步：${tools.join("、")}。`
            : "本轮意图：模型没有继续调用工具，开始进入报告整理或结果收尾。",
          `完成原因：${String(data.finish_reason ?? "未知")}`,
          duration !== undefined ? `耗时：${duration} ms` : "",
          usage,
          toolArguments ? `\n工具参数摘要：\n${toolArguments}` : "",
        ].filter(Boolean).join("\n"),
      };
    }
    case "planner_tool_requested": {
      const tool = humanToolName(data.tool);
      const args = data.arguments ? JSON.stringify(data.arguments, null, 2) : "";
      return {
        role: "tool",
        title: tool,
        status: "进行中",
        preview: `正在${tool}。`,
        mergeKey: streamEventMergeKey(event),
        body: [
          `开始：系统开始${tool}。`,
          args ? `\n传给工具的参数摘要：\n${args}` : "",
        ].filter(Boolean).join("\n"),
      };
    }
    case "planner_tool_completed": {
      const tool = humanToolName(data.tool);
      const result = data.result ? JSON.stringify(data.result, null, 2) : "";
      const resultRecord = asRecord(data.result);
      const toolOutputSummary = String(data.tool) === "execute_code" && Object.keys(resultRecord).length
        ? outputCountSentence(resultRecord)
        : "";
      return {
        role: "tool",
        title: tool,
        status: "完成",
        preview: toolOutputSummary ? `${tool}已完成 · ${toolOutputSummary}` : `${tool}已完成。`,
        mergeKey: streamEventMergeKey(event),
        body: [
          `完成：${summarizePlannerToolResult(data.tool, data.result, summary)}`,
          result ? `\n工具返回摘要：\n${result}` : "",
        ].filter(Boolean).join("\n"),
      };
    }
    case "feedback_evaluated":
      return {
        role: "system",
        title: "检查分析质量",
        status: data.should_retry ? "需要补充" : "通过",
        body: data.should_retry
          ? "系统发现当前分析还不够完整，会让模型补充证据、修复问题或完善报告。"
          : "系统已检查报告质量，当前结果可以进入收尾。",
      };
    case "planner_finalization_forced":
      return {
        role: "assistant",
        title: "进入报告收尾",
        status: "收尾中",
        body: "系统已经完成必要的数据计算和质量检查，接下来会基于已有结果整理最终报告，不再继续扩展新的分析步骤。",
      };
    case "planner_finalizer_length_truncated":
      return {
        role: "assistant",
        title: "报告收尾被截断",
        status: "重试中",
        preview: `第 ${String(data.length_truncation_count ?? "?")} 次截断 · 将压缩后重试`,
        body: [
          "模型在最终报告收尾时触发长度截断，系统会压缩上下文或切换收尾策略后重试。",
          `完成 token：${String(data.completion_tokens ?? "未知")}`,
          `内容字符数：${String(data.content_chars ?? "未知")}`,
          `下一步：${String(data.next_action ?? "retry")}`,
        ].join("\n"),
      };
    case "planner_final_output_rejected":
      return {
        role: "assistant",
        title: "最终输出格式未通过",
        status: "需修复",
        preview: "模型输出不是可直接解析的最终报告结构。",
        body: summary || "系统拒绝了当前最终输出，将要求模型修复为结构化 JSON 报告。",
      };
    case "planner_final_output_format_repair_started":
      return {
        role: "assistant",
        title: "报告格式修复",
        status: "进行中",
        preview: `第 ${String(data.attempt ?? "?")} 次修复开始。`,
        body: summary || "系统正在把模型最终输出修复为可解析、可验证的结构化报告。",
      };
    case "planner_final_output_format_repair_completed": {
      const attempt = String(data.attempt ?? "?");
      const chars = String(data.repaired_report_chars ?? data.content_chars ?? "未知");
      return {
        role: "assistant",
        title: "报告格式修复完成",
        status: "已恢复",
        preview: `第 ${attempt} 次修复完成 · ${chars} 字`,
        body: [
          summary,
          `已把模型输出修复为可解析的结构化报告。`,
          `修复后报告字符数：${chars}`,
        ].filter(Boolean).join("\n"),
      };
    }
    case "planner_final_output_format_repair_failed":
      return {
        role: "assistant",
        title: "报告格式修复失败",
        status: "失败",
        preview: `第 ${String(data.attempt ?? "?")} 次修复失败。`,
        body: summary || "系统尝试修复最终报告格式失败，会继续进入 fallback 或报告限制说明。",
      };
    case "planner_final_payload_parsed": {
      const reportChars = String(data.report_md_chars ?? "未知");
      const chartCount = numberValue(data.chart_specs_count ?? data.chart_ref_count);
      const tableCount = numberValue(data.table_specs_count ?? data.table_ref_count);
      const angleCount = numberValue(data.candidate_angles_count);
      const preview = [
        `${reportChars} 字`,
        chartCount !== undefined ? countLabel(chartCount, "图表") : "",
        tableCount !== undefined ? countLabel(tableCount, "表格") : "",
      ].filter(Boolean).join(" · ");
      return {
        role: "report",
        title: "最终报告结构校验",
        status: data.schema_valid === false ? "需关注" : "完成",
        preview,
        body: [
          `解析策略：${String(data.parse_strategy ?? "未知")}`,
          `报告正文：${reportChars} 字符`,
          chartCount !== undefined ? `图表规划：${chartCount} 个` : "",
          tableCount !== undefined ? `表格规划：${tableCount} 个` : "",
          angleCount !== undefined ? `候选分析角度：${angleCount} 个` : "",
          Array.isArray(data.quality_flags) && data.quality_flags.length
            ? `质量标记：${data.quality_flags.map(String).join("、")}`
            : "质量标记：无",
        ].filter(Boolean).join("\n"),
      };
    }
    case "planner_finalized":
      return {
        role: "report",
        title: "最终报告已整理",
        status: "完成",
        body: "模型已返回结构化报告内容，系统会继续生成报告产物并执行验证。",
      };
    default:
      return {
        role: "system",
        title: event.type
          ? `分析步骤：${String(event.type).replace(/_/g, " ")}`
          : "分析步骤",
        status: "实时",
        body: summary || "事件已记录。",
      };
  }
}

function buildCompletedMessages(run: RunResponse): TimelineMessage[] {
  const messages: TimelineMessage[] = [
    {
      role: "user",
      title: "用户分析提示词",
      body: run.question,
      status: run.status,
    },
  ];

  for (const step of run.workflow_steps) {
    messages.push({
      role: "assistant",
      title: `工作流步骤：${step.name}`,
      status: translateStatus(step.status),
      body: step.summary || "步骤已记录。",
    });
  }

  const planArtifact = run.artifacts.find((artifact) => artifact.title === "分析计划");
  if (planArtifact?.content) {
    messages.push({
      role: "assistant",
      title: "模型分析计划",
      status: "已生成",
      body: truncateText(planArtifact.content, 1600),
    });
  }

  for (const call of run.tool_calls) {
    messages.push({
      role: "tool",
      title: `工具调用：${call.name}`,
      status: translateStatus(call.status),
      body: call.output_summary || call.input_summary || "工具调用已记录。",
    });
  }

  const artifactSummary = summarizeArtifacts(run.artifacts);
  if (artifactSummary) {
    messages.push({
      role: "tool",
      title: "分析产物",
      status: "已生成",
      body: artifactSummary,
    });
  }

  const reportArtifact = pickReportArtifact(run.artifacts);
  if (reportArtifact?.content) {
    messages.push({
      role: "report",
      title: "最终报告",
      status: "已完成",
      body: truncateText(reportArtifact.content, 2600),
    });
  }

  if (run.validation_results?.length) {
    const passed = run.validation_results.filter((item) => item.passed).length;
    messages.push({
      role: "system",
      title: "验证结果",
      status: run.validation_passed ? "通过" : "需关注",
      body: [`${passed}/${run.validation_results.length} 个验证项通过。`, ...run.validation_results.map((item) => `${item.passed ? "✓" : "!"} ${item.gate_id}: ${item.message}`)].join("\n"),
    });
  }

  return messages;
}

function getMessagePreview(message: TimelineMessage) {
  if (message.preview !== undefined) return message.preview;
  if (!message.body.trim()) return "";

  if (message.role === "code") {
    const lineCount = message.body.split("\n").length;
    return `代码已生成（${lineCount} 行），点击查看完整代码。`;
  }

  if (message.compact) return "";
  return firstLinePreview(message.body, 96);
}

function firstLinePreview(text: string, limit: number) {
  const firstLine = text
    .replace(/\r/g, "")
    .split("\n")
    .map((line) => line.trim())
    .find(Boolean) || "";

  if (firstLine.length <= limit) return firstLine;
  return `${firstLine.slice(0, limit).trim()}…`;
}

function summarizeArtifacts(artifacts: Artifact[]): string {
  const tables = artifacts.filter((artifact) => artifact.type === "table");
  const charts = artifacts.filter((artifact) => artifact.type === "chart");
  const reports = artifacts.filter((artifact) => ["markdown_report", "html_report", "structured_report", "visual_report"].includes(artifact.type));
  const notebooks = artifacts.filter((artifact) => artifact.type === "notebook");
  const parts = [
    tables.length ? `表格：${tables.map((item) => item.title).join("、")}` : "",
    charts.length ? `图表：${charts.map((item) => item.title).join("、")}` : "",
    reports.length ? `报告：${reports.map((item) => item.title).join("、")}` : "",
    notebooks.length ? `Notebook：${notebooks.map((item) => item.title).join("、")}` : "",
  ].filter(Boolean);
  return parts.join("\n");
}

function pickReportArtifact(artifacts: Artifact[]) {
  return (
    artifacts.find((artifact) => artifact.type === "visual_report") ??
    artifacts.find((artifact) => artifact.type === "markdown_report") ??
    artifacts.find((artifact) => artifact.type === "structured_report")
  );
}

function translateStatus(status: string) {
  const mapping: Record<string, string> = {
    blocked: "已阻止",
    completed: "已完成",
    completed_with_warnings: "有警告",
    failed: "失败",
    pending: "等待中",
    running: "进行中",
    warning: "有警告",
  };
  return mapping[status] ?? status;
}

function truncateText(text: string, limit: number) {
  if (text.length <= limit) return text;
  return `${text.slice(0, limit).trim()}\n\n……内容较长，已在此处截断。完整内容可到「报告产物」或「任务回放」查看。`;
}
