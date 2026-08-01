import { useEffect, useMemo, useState } from "react";
import type { AnalysisProject, ProjectContext, Skill } from "../types";
import { emptyContextForm } from "../shared";
import {
  fetchSkills,
  fetchProjects,
  createProject as apiCreateProject,
  updateProject as apiUpdateProject,
  fetchContexts,
  createContext as apiCreateContext,
  updateContext as apiUpdateContext,
  deleteContext as apiDeleteContext,
} from "../api";

export function useProjects(onError: (msg: string) => void) {
  const [skills, setSkills] = useState<Skill[]>([]);
  const [projects, setProjects] = useState<AnalysisProject[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [contexts, setContexts] = useState<ProjectContext[]>([]);
  const [selectedContextIds, setSelectedContextIds] = useState<string[]>([]);
  const [projectDraft, setProjectDraft] = useState({ name: "", description: "" });
  const [newProjectDraft, setNewProjectDraft] = useState({ name: "", description: "" });
  const [contextDraft, setContextDraft] = useState(emptyContextForm);
  const [editingContextId, setEditingContextId] = useState("");
  const [isSavingProject, setIsSavingProject] = useState(false);
  const [isSavingContext, setIsSavingContext] = useState(false);

  const selectedProject = useMemo(
    () => projects.find((project) => project.id === selectedProjectId),
    [projects, selectedProjectId]
  );

  const selectedContexts = useMemo(
    () => contexts.filter((context) => selectedContextIds.includes(context.id)),
    [contexts, selectedContextIds]
  );

  useEffect(() => {
    fetchSkills()
      .then(setSkills)
      .catch((err) => { onError(err instanceof Error ? err.message : String(err)); setSkills([]); });
    refreshProjects();
  }, []);

  useEffect(() => {
    setSelectedContextIds([]);
    if (!selectedProjectId) {
      setContexts([]);
      setProjectDraft({ name: "", description: "" });
      return;
    }
    fetchContexts(selectedProjectId)
      .then((nextContexts) => {
        setContexts(nextContexts);
        setSelectedContextIds(nextContexts.map((context) => context.id));
      })
      .catch((err) => {
        onError(err instanceof Error ? err.message : String(err));
        setContexts([]);
        setSelectedContextIds([]);
      });
  }, [selectedProjectId]);

  useEffect(() => {
    if (!selectedProject) return;
    setProjectDraft({
      name: selectedProject.name,
      description: selectedProject.description,
    });
  }, [selectedProject]);

  async function refreshProjects(preferredProjectId?: string) {
    const nextProjects = await fetchProjects().catch((err) => {
      onError(err instanceof Error ? err.message : String(err));
      return [] as AnalysisProject[];
    });
    setProjects(nextProjects);
    setSelectedProjectId((current) => {
      if (preferredProjectId) return preferredProjectId;
      if (current && nextProjects.some((project) => project.id === current)) return current;
      return nextProjects[0]?.id ?? "";
    });
  }

  async function createProject() {
    if (!newProjectDraft.name.trim()) return;
    try {
      const project = await apiCreateProject(newProjectDraft.name, newProjectDraft.description);
      setNewProjectDraft({ name: "", description: "" });
      await refreshProjects(project.id);
    } catch (err) {
      onError(err instanceof Error ? err.message : String(err));
    }
  }

  async function saveProject() {
    if (!selectedProjectId || !projectDraft.name.trim()) return;
    setIsSavingProject(true);
    try {
      const updated = await apiUpdateProject(selectedProjectId, projectDraft);
      await refreshProjects(updated.id);
    } catch (err) {
      onError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsSavingProject(false);
    }
  }

  async function archiveProject() {
    if (!selectedProjectId) return;
    try {
      await apiUpdateProject(selectedProjectId, { status: "archived" });
      setContexts([]);
      setSelectedContextIds([]);
      await refreshProjects();
    } catch (err) {
      onError(err instanceof Error ? err.message : String(err));
    }
  }

  async function saveContext() {
    if (!selectedProjectId || !contextDraft.title.trim() || !contextDraft.body.trim()) return;
    setIsSavingContext(true);
    try {
      if (editingContextId) {
        await apiUpdateContext(selectedProjectId, editingContextId, contextDraft);
      } else {
        await apiCreateContext(selectedProjectId, contextDraft);
      }
      setContextDraft(emptyContextForm);
      setEditingContextId("");
      const nextContexts = await fetchContexts(selectedProjectId);
      setContexts(nextContexts);
      setSelectedContextIds(nextContexts.map((context) => context.id));
      await refreshProjects(selectedProjectId);
    } catch (err) {
      onError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsSavingContext(false);
    }
  }

  async function deleteContext(contextId: string) {
    if (!selectedProjectId) return;
    try {
      await apiDeleteContext(selectedProjectId, contextId);
      const nextContexts = await fetchContexts(selectedProjectId);
      setContexts(nextContexts);
      setSelectedContextIds((current) => current.filter((id) => id !== contextId));
      if (editingContextId === contextId) {
        setEditingContextId("");
        setContextDraft(emptyContextForm);
      }
    } catch (err) {
      onError(err instanceof Error ? err.message : String(err));
    }
  }

  function editContext(context: ProjectContext) {
    setEditingContextId(context.id);
    setContextDraft({
      kind: context.kind,
      title: context.title,
      body: context.body,
    });
  }

  function toggleContext(contextId: string) {
    setSelectedContextIds((current) =>
      current.includes(contextId) ? current.filter((id) => id !== contextId) : [...current, contextId]
    );
  }

  return {
    skills,
    projects,
    selectedProjectId,
    selectedProject,
    contexts,
    selectedContextIds,
    selectedContexts,
    projectDraft,
    newProjectDraft,
    contextDraft,
    editingContextId,
    isSavingProject,
    isSavingContext,
    setSelectedProjectId,
    setProjectDraft,
    setNewProjectDraft,
    setContextDraft,
    setEditingContextId,
    refreshProjects,
    createProject,
    saveProject,
    archiveProject,
    saveContext,
    deleteContext,
    editContext,
    toggleContext,
  };
}
