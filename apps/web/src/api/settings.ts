import { requestJson } from "../apiClient";

export function fetchSettings(): Promise<{ generated_code_execution: string }> {
  return requestJson<{ generated_code_execution: string }>("/api/settings");
}
