import { afterEach, describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { fetchRuns } from "../src/api/runs";
import { isWebReportArtifact, webReportAssetUrl } from "../src/components/ArtifactModule";
import { buildExecutionChain, buildLlmTuningLog } from "../src/components/TraceModule";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("workbench navigation", () => {
  it("removes the standalone validation/export module from navigation", () => {
    const app = readFileSync(resolve(__dirname, "../src/App.tsx"), "utf-8");
    const types = readFileSync(resolve(__dirname, "../src/types.ts"), "utf-8");

    expect(app).not.toContain("ValidationModule");
    expect(app).not.toContain("验证与导出");
    expect(types).not.toContain('"validation"');
  });
});

describe("historical reports", () => {
  it("fetches persisted runs for report history", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify([
        {
          id: "run-1",
          status: "completed",
          question: "分析销售趋势",
          artifact_count: 3,
          tool_call_count: 2,
          workflow_step_count: 4,
          has_visual_report: true,
        },
      ]), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );

    const runs = await fetchRuns("project-1");

    expect(globalThis.fetch).toHaveBeenCalledWith("/api/runs?project_id=project-1", expect.any(Object));
    expect(runs[0].question).toBe("分析销售趋势");
    expect(runs[0].has_visual_report).toBe(true);
  });
});

describe("task replay execution chain", () => {
  it("groups low-level trace events into readable execution phases", () => {
    const chain = buildExecutionChain([
      { id: "e1", order: 1, type: "run_started", name: "任务启动", status: "completed", data: {} },
      { id: "e2", order: 2, type: "llm_request_started", name: "LLM 请求", status: "running", data: { iteration: 1, phase: "analysis" } },
      { id: "e3", order: 3, type: "planner_tool_completed", name: "工具结果", status: "completed", data: { tool: "execute_code" } },
      { id: "e4", order: 4, type: "code_execution_completed", name: "执行结果", status: "completed", data: { table_count: 2, chart_count: 1 } },
      { id: "e5", order: 5, type: "planner_final_payload_parsed", name: "Payload", status: "completed", data: { report_md_chars: 8000 } },
      { id: "e6", order: 6, type: "validation_completed", name: "验证完成", status: "passed", data: { validation_passed: true, pass_count: 28, gate_count: 28 } },
    ]);

    expect(chain.map((phase) => phase.id)).toEqual(["prepare", "model", "tools", "report", "validation"]);
    expect(chain[1].summary).toContain("1 次模型调用");
    expect(chain[2].summary).toContain("2 个表格");
    expect(chain[2].summary).toContain("1 个图表");
    expect(chain[4].summary).toContain("28/28");
  });
});

describe("LLM tuning log", () => {
  it("builds readable model-round diagnostics from trace events", () => {
    const log = buildLlmTuningLog({
      run: {
        id: "run-1",
        status: "completed",
        question: "分析销售趋势",
        artifact_count: 1,
        tool_call_count: 1,
        workflow_step_count: 1,
      },
      event_count: 3,
      schema_version: 2,
      events: [
        {
          id: "e1",
          order: 1,
          type: "llm_request_started",
          name: "LLM 请求",
          status: "running",
          data: {
            iteration: 1,
            phase: "analysis",
            model: "deepseek-chat",
            message_count: 4,
            estimated_context_chars: 12000,
            available_tools: ["execute_code"],
            prompt_snapshot: {
              message_count: 4,
              included_message_count: 4,
              omitted_message_count: 0,
              messages: [
                { index: 0, role: "system", content_chars: 12, content_preview: { head: "规则" } },
              ],
            },
          },
        },
        {
          id: "e2",
          order: 2,
          type: "llm_request_completed",
          name: "LLM 响应",
          status: "completed",
          data: {
            iteration: 1,
            finish_reason: "tool_calls",
            latency_ms: 1500,
            usage: { prompt_tokens: 1000, completion_tokens: 200, total_tokens: 1200 },
            requested_tool_names: ["execute_code"],
          },
        },
        {
          id: "e3",
          order: 3,
          type: "planner_tool_requested",
          name: "工具请求",
          status: "running",
          data: { iteration: 1, tool: "execute_code", arguments: { step_name: "sales" } },
        },
      ],
    });

    expect(log.requestCount).toBe(1);
    expect(log.totalPromptTokens).toBe(1000);
    expect(log.rounds[0].model).toBe("deepseek-chat");
    expect(log.rounds[0].finishReason).toBe("tool_calls");
    expect(log.rounds[0].toolRequests).toHaveLength(1);
    expect(log.rounds[0].promptSnapshot?.messages?.[0].role).toBe("system");
  });
});

describe("quarto report preview", () => {
  it("recognizes quarto html artifacts and builds same-window asset urls", () => {
    const artifact = {
      id: "a1",
      type: "html_report",
      title: "网页版报告",
      path: "/tmp/web_report.html",
      data: { renderer: "quarto_html" },
    };

    expect(isWebReportArtifact(artifact)).toBe(true);
    expect(webReportAssetUrl(artifact, "run-1")).toBe("/api/runs/run-1/assets/web_report.html");
  });
});
