import { requestJson, requestVoid } from "../apiClient";
import type { AnalysisProject, ProjectContext, Skill } from "../types";

export function fetchSkills(): Promise<Skill[]> {
  return requestJson<Skill[]>("/api/skills");
}

export function fetchProjects(): Promise<AnalysisProject[]> {
  return requestJson<AnalysisProject[]>("/api/projects");
}

export function createProject(name: string, description: string): Promise<AnalysisProject> {
  return requestJson<AnalysisProject>("/api/projects", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, description }),
  });
}

export function updateProject(
  projectId: string,
  payload: Partial<Pick<AnalysisProject, "name" | "description" | "status">>
): Promise<AnalysisProject> {
  return requestJson<AnalysisProject>(`/api/projects/${projectId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function fetchContexts(projectId: string): Promise<ProjectContext[]> {
  return requestJson<ProjectContext[]>(`/api/projects/${projectId}/contexts`);
}

export function createContext(
  projectId: string,
  payload: Pick<ProjectContext, "kind" | "title" | "body">
): Promise<ProjectContext> {
  return requestJson<ProjectContext>(`/api/projects/${projectId}/contexts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function updateContext(
  projectId: string,
  contextId: string,
  payload: Pick<ProjectContext, "kind" | "title" | "body">
): Promise<ProjectContext> {
  return requestJson<ProjectContext>(`/api/projects/${projectId}/contexts/${contextId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function deleteContext(projectId: string, contextId: string): Promise<void> {
  return requestVoid(`/api/projects/${projectId}/contexts/${contextId}`, {
    method: "DELETE",
  });
}
