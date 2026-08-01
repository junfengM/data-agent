import type { ProjectContext, RunResponse, RunSummary } from "../types";
import { apiFetch, requestJson } from "../apiClient";

export type RunStreamEvent = {
  kind?: "event" | "result" | "error";
  type?: string;
  summary?: string;
  data?: Record<string, unknown>;
};

export function selectedContextsToMarkdown(contexts: ProjectContext[]): string {
  if (!contexts.length) return "";
  return [
    "本次运行指定使用以下项目上下文。未勾选的上下文不应作为本次分析依据。",
    "",
    ...contexts.flatMap((context) => [
      `## ${context.title} (${context.kind})`,
      context.body,
      "",
    ]),
  ].join("\n").trim();
}

export async function readStreamingRun(
  response: Response,
  onEvent: (event: RunStreamEvent) => void
): Promise<RunResponse> {
  if (!response.ok) {
    let detail = "运行失败";
    try {
      const payload = await response.json();
      detail = payload.detail ?? detail;
    } catch {
      detail = await response.text().catch(() => detail);
    }
    throw new Error(detail);
  }
  if (!response.body) {
    throw new Error("浏览器不支持流式读取运行事件");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finalRun: RunResponse | null = null;

  function consumeChunk(chunk: string) {
    buffer += chunk;
    let boundary = buffer.indexOf("\n\n");
    while (boundary >= 0) {
      const rawEvent = buffer.slice(0, boundary).trim();
      buffer = buffer.slice(boundary + 2);
      boundary = buffer.indexOf("\n\n");
      const dataLine = rawEvent.split("\n").find((line) => line.startsWith("data:"));
      if (!dataLine) continue;
      const payload = JSON.parse(dataLine.slice(5).trim()) as RunStreamEvent & { run?: RunResponse };
      if (payload.kind === "event") {
        onEvent(payload);
      } else if (payload.kind === "result" && payload.run) {
        finalRun = payload.run;
      } else if (payload.kind === "error") {
        throw new Error(payload.summary || "运行失败");
      }
    }
  }

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    consumeChunk(decoder.decode(value, { stream: true }));
  }
  consumeChunk(decoder.decode());

  if (!finalRun) {
    throw new Error("运行结束但没有收到最终结果");
  }
  return finalRun;
}

export async function streamRun(params: {
  question: string;
  skillId?: string;
  datasetIds: string[];
  projectId?: string;
  context?: string;
  modelConfigId?: string;
  runMode?: string;
  onEvent: (event: RunStreamEvent) => void;
}): Promise<RunResponse> {
  const response = await apiFetch("/api/runs/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question: params.question,
      project_id: params.projectId || null,
      skill_id: params.skillId || null,
      dataset_ids: params.datasetIds,
      context: params.context || null,
      model_config_id: params.modelConfigId || null,
      run_mode: params.runMode || "full",
    }),
  });
  return readStreamingRun(response, params.onEvent);
}

export function fetchRun(runId: string, projectId?: string): Promise<RunResponse> {
  const query = projectId ? `?project_id=${encodeURIComponent(projectId)}` : "";
  return requestJson<RunResponse>(`/api/runs/${runId}${query}`);
}

export function cancelRun(runId: string): Promise<{ run_id: string; status: string }> {
  return requestJson(`/api/runs/${encodeURIComponent(runId)}/cancel`, {
    method: "POST",
  });
}

export function fetchRuns(projectId?: string): Promise<RunSummary[]> {
  const query = projectId ? `?project_id=${encodeURIComponent(projectId)}` : "";
  return requestJson<RunSummary[]>(`/api/runs${query}`);
}
