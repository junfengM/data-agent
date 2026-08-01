import { useEffect, useState } from "react";
import type { ModelConfig } from "../types";
import { fetchModels, fetchSettings } from "../api";

export function useModels(onError: (msg: string) => void) {
  const [models, setModels] = useState<ModelConfig[]>([]);
  const [selectedModelId, setSelectedModelId] = useState("");
  const [generatedCodeExecution, setGeneratedCodeExecution] = useState("disabled");

  useEffect(() => {
    fetchModels()
      .then((payload) => {
        setModels(payload.models);
        setSelectedModelId(
          (current) => current || payload.default_model || payload.models[0]?.id || ""
        );
      })
      .catch((err) => {
        onError(err instanceof Error ? err.message : String(err));
        setModels([]);
      });
    fetchSettings()
      .then((payload) => setGeneratedCodeExecution(payload.generated_code_execution))
      .catch((err) => { onError(err instanceof Error ? err.message : String(err)); });
  }, []);

  return {
    models,
    selectedModelId,
    generatedCodeExecution,
    setModels,
    setSelectedModelId,
  };
}
