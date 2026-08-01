import { useRef, useState } from "react";
import type { ProjectContext, RunResponse } from "../types";
import {
  cancelRun,
  streamRun,
  selectedContextsToMarkdown,
  RunStreamEvent,
} from "../api";

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
  const cancelRequestedRef = useRef(false);
  const activeRunIdRef = useRef<string | null>(null);

  async function createRun() {
    setIsRunning(true);
    cancelRequestedRef.current = false;
    activeRunIdRef.current = null;
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
        onEvent: (event) => {
          const eventRunId = event.data?.run_id;
          if (typeof eventRunId === "string" && eventRunId) {
            activeRunIdRef.current = eventRunId;
          }
          setRunEvents((current) => [...current, event]);
        },
      });
      cancelRequestedRef.current = false;
      setRun(result);
      return result;
    } catch (err) {
      if (cancelRequestedRef.current) {
        // Cancellation was requested by the user; treat the closed stream as expected.
        return undefined;
      }
      throw err;
    } finally {
      setIsRunning(false);
    }
  }

  async function cancelCurrentRun() {
    cancelRequestedRef.current = true;
    const runId = activeRunIdRef.current;
    if (!runId) return;
    try {
      await cancelRun(runId);
    } catch {
      // Backend may already have finished the run; nothing else to do.
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
    cancelRun: cancelCurrentRun,
    setRun,
    setRunEvents,
  };
}
