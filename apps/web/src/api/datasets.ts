import { requestJson } from "../apiClient";
import type { Dataset } from "../types";

export function fetchDatasets(projectId?: string): Promise<Dataset[]> {
  const query = projectId ? `?project_id=${encodeURIComponent(projectId)}` : "";
  return requestJson<Dataset[]>(`/api/datasets${query}`);
}

export function uploadDataset(
  file: File,
  projectId?: string
): Promise<{ dataset_id: string; filename: string; path: string }> {
  const body = new FormData();
  body.append("file", file);
  const query = projectId ? `?project_id=${encodeURIComponent(projectId)}` : "";
  return requestJson<{ dataset_id: string; filename: string; path: string }>(`/api/files${query}`, {
    method: "POST",
    body,
  });
}
