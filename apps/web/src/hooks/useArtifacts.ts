import { useEffect, useMemo, useState } from "react";
import type { RunResponse } from "../types";

export function preferredArtifactId(run: RunResponse): string {
  return (
    run.artifacts.find((artifact) => artifact.type === "visual_report") ??
    run.artifacts.find((artifact) => artifact.type === "structured_report") ??
    run.artifacts.find((artifact) => artifact.type === "markdown_report") ??
    run.artifacts[0]
  )?.id ?? "";
}

export function useArtifacts(run: RunResponse | null) {
  const [activeArtifactId, setActiveArtifactId] = useState("");

  const activeArtifact = useMemo(
    () =>
      run?.artifacts.find((artifact) => artifact.id === activeArtifactId) ??
      run?.artifacts.find((artifact) => artifact.type === "visual_report") ??
      run?.artifacts[0],
    [activeArtifactId, run]
  );

  useEffect(() => {
    if (run) {
      setActiveArtifactId(preferredArtifactId(run));
    }
  }, [run]);

  return {
    activeArtifactId,
    activeArtifact,
    setActiveArtifactId,
  };
}
