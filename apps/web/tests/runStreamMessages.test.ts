import { describe, expect, it } from "vitest";
import { messageFromStreamEvent, type RunStreamEvent } from "../src/components/RunModule";

function render(event: RunStreamEvent) {
  return messageFromStreamEvent({ kind: "event", ...event });
}

describe("run stream messages", () => {
  it("summarizes code execution outputs in the visible preview", () => {
    const message = render({
      type: "code_execution_completed",
      data: {
        step_name: "品类趋势分析",
        returncode: 0,
        table_count: 2,
        chart_count: 3,
        stdout: "wrote category_summary.csv\nwrote monthly_trend.html",
      },
    });

    expect(message.title).toBe("执行数据计算：品类趋势分析");
    expect(message.status).toBe("完成");
    expect(message.preview).toContain("2 个表格");
    expect(message.preview).toContain("3 个图表");
    expect(message.body).toContain("产出：2 个表格、3 个图表");
    expect(message.body).toContain("关键输出");
  });

  it("shows validation gate pass ratio, failures, and warnings", () => {
    const message = render({
      type: "validation_completed",
      summary: "验证完成：28/28 gates passed。",
      data: {
        validation_passed: true,
        pass_count: 28,
        gate_count: 28,
        fail_count: 0,
        warning_count: 0,
      },
    });

    expect(message.status).toBe("通过");
    expect(message.preview).toContain("28/28 通过");
    expect(message.preview).toContain("0 失败");
    expect(message.preview).toContain("0 警告");
    expect(message.body).toContain("报告已通过质量门禁");
  });

  it("turns finalizer payload parsing into a report structure milestone", () => {
    const message = render({
      type: "planner_final_payload_parsed",
      data: {
        parse_strategy: "format_repair",
        report_md_chars: 7549,
        chart_specs_count: 4,
        table_specs_count: 4,
        candidate_angles_count: 5,
      },
    });

    expect(message.title).toBe("最终报告结构校验");
    expect(message.status).toBe("完成");
    expect(message.preview).toContain("7549 字");
    expect(message.preview).toContain("4 个图表");
    expect(message.preview).toContain("4 个表格");
    expect(message.body).toContain("候选分析角度：5 个");
  });

  it("explains finalizer format repair as a recovery event", () => {
    const message = render({
      type: "planner_final_output_format_repair_completed",
      data: {
        attempt: 1,
        repaired_report_chars: 8320,
      },
    });

    expect(message.title).toBe("报告格式修复完成");
    expect(message.status).toBe("已恢复");
    expect(message.preview).toContain("第 1 次修复");
    expect(message.preview).toContain("8320 字");
    expect(message.body).toContain("已把模型输出修复为可解析的结构化报告");
  });

  it("keeps model decisions readable instead of dumping raw JSON first", () => {
    const message = render({
      type: "llm_request_completed",
      data: {
        iteration: 2,
        requested_tools: ["execute_code"],
        finish_reason: "tool_calls",
        usage: { prompt_tokens: 1000, completion_tokens: 200, total_tokens: 1200 },
        tool_arguments: [{ tool: "execute_code", arguments: { step_name: "趋势分析" } }],
      },
    });

    expect(message.preview).toContain("下一步：执行数据计算");
    expect(message.body).toContain("本轮意图：调用工具继续推进分析");
    expect(message.body).toContain("Token：1200");
    expect(message.body).not.toContain("\"prompt_tokens\"");
  });

  it("summarizes backend tool argument metadata with step names", () => {
    const message = render({
      type: "llm_request_completed",
      data: {
        requested_tool_names: ["execute_code"],
        tool_arguments: [{ valid_json: true, keys: ["code", "step_name"], step_name: "趋势分析", code_chars: 4096 }],
      },
    });

    expect(message.body).toContain("1. 执行数据计算：趋势分析 · 4096 字符代码");
  });

  it("includes prompt snapshots for each model request", () => {
    const message = render({
      type: "llm_request_started",
      data: {
        iteration: 3,
        phase: "finalize",
        message_count: 2,
        prompt_chars: 1200,
        prompt_snapshot: {
          message_count: 2,
          included_message_count: 2,
          omitted_message_count: 0,
          total_content_chars: 1200,
          messages: [
            {
              index: 0,
              role: "system",
              content_chars: 800,
              content_preview: { head: "You are the Data Agent router.", tail: "", truncated: false },
              tool_calls: [],
            },
            {
              index: 1,
              role: "user",
              content_chars: 400,
              content_preview: { head: "用户问题：分析 2026-06-15 后的 planner/finalizer。", tail: "", truncated: false },
              tool_calls: [
                {
                  name: "execute_code",
                  arguments_preview: { head: "{\"step_name\":\"验证 planner\"}", tail: "", truncated: false },
                },
              ],
            },
          ],
        },
      },
    });

    expect(message.preview).toContain("第 3 次模型调用开始");
    expect(message.body).toContain("Prompt 快照：2/2 条消息");
    expect(message.body).toContain("#0 system");
    expect(message.body).toContain("You are the Data Agent router.");
    expect(message.body).toContain("#1 user");
    expect(message.body).toContain("验证 planner");
    expect(message.body).toContain("tool_call 1：execute_code");
  });
});
