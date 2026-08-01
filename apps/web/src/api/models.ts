import { requestJson } from "../apiClient";
import type { ModelConfig } from "../types";

export function fetchModels(): Promise<{ default_model?: string; models: ModelConfig[] }> {
  return requestJson<{ default_model?: string; models: ModelConfig[] }>("/api/models");
}
