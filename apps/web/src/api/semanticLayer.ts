import type { SemanticLayerMeta } from "../types";
import { apiFetch } from "../apiClient";

export async function fetchActiveSemanticLayer(projectId: string): Promise<SemanticLayerMeta | null> {
  const response = await apiFetch(`/api/projects/${projectId}/semantic-layers/active`);
  if (!response.ok) return null;
  return response.json();
}
