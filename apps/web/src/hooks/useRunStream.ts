import { useState } from "react";
import type { ProjectContext, RunResponse } from "../types";
import { streamRun, selectedContextsToMarkdown, RunStreamEvent } from "../api";

export function useRunStream(deps: {
  selectedProjectId: string;
  selectedContexts: ProjectContext[];
  selectedModelId: string;
  selectedDatasetIds: string[];
}) {
  const [question, setQuestion] = useState(
    "请分析当前数据，先给出诊断结论，再生成一份可分享的中文报告。"
  );
  const [selectedSkill, setSelectedSkill] = useState("");
  const [run, setRun] = useState<RunResponse | null>(null);
  const [runEvents, setRunEvents] = useState<RunStreamEvent[]>([]);
  const [isRunning, setIsRunning] = useState(false);

  async function createRun() {
    setIsRunning(true);
    setRun(null);
    setRunEvents([]);
    try {
      const result = await streamRun({
        question,
        skillId: selectedSkill,
        datasetIds: deps.selectedDatasetIds,
        projectId: deps.selectedProjectId,
        context: selectedContextsToMarkdown(deps.selectedContexts),
        modelConfigId: deps.selectedModelId,
        runMode: "full",
        onEvent: (event) => setRunEvents((current) => [...current, event]),
      });
      setRun(result);
      return result;
    } finally {
      setIsRunning(false);
    }
  }

  return {
    question,
    selectedSkill,
    run,
    runEvents,
    isRunning,
    setQuestion,
    setSelectedSkill,
    createRun,
    setRun,
    setRunEvents,
  };
}
