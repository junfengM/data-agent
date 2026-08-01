import React, { useState } from "react";
import {
  Activity,
  BarChart3,
  Boxes,
  Database,
  FileText,
  FolderKanban,
  Layers,
  Play,
  Settings,
  X,
} from "lucide-react";
import type { ModuleId } from "./types";
import { fetchRun } from "./api";
import { useProjects } from "./hooks/useProjects";
import { useModels } from "./hooks/useModels";
import { useDatasets } from "./hooks/useDatasets";
import { useSemanticLayer } from "./hooks/useSemanticLayer";
import { useRunStream } from "./hooks/useRunStream";
import { useArtifacts } from "./hooks/useArtifacts";
import ProjectModule from "./components/ProjectModule";
import DataModule from "./components/DataModule";
import ContextModule from "./components/ContextModule";
import SemanticLayerModule from "./components/SemanticLayerModule";
import RunModule from "./components/RunModule";
import ArtifactModule from "./components/ArtifactModule";
import TraceModule from "./components/TraceModule";
import SystemSettingsPanel from "./components/SystemSettingsPanel";
import "./styles.css";
import "./trace.css";
import "./tokens.css";

const modules: Array<{ id: ModuleId; label: string; icon: React.ElementType }> = [
  { id: "run", label: "分析运行", icon: Play },
  { id: "projects", label: "项目", icon: FolderKanban },
  { id: "data", label: "数据", icon: Database },
  { id: "context", label: "上下文", icon: Boxes },
  { id: "semantic-layer", label: "语义层", icon: Layers },
  { id: "artifacts", label: "报告产物", icon: FileText },
  { id: "trace", label: "任务回放", icon: Activity },
];

export default function App() {
  const [activeModule, setActiveModule] = useState<ModuleId>("run");
  const [showSystemInfo, setShowSystemInfo] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");

  const onError = (msg: string) => setErrorMessage(msg);

  const projects = useProjects(onError);
  const models = useModels(onError);
  const dataState = useDatasets(projects.selectedProjectId, onError);
  const semantic = useSemanticLayer(projects.selectedProjectId, onError);
  const runStream = useRunStream({
    selectedProjectId: projects.selectedProjectId,
    selectedContexts: projects.selectedContexts,
    selectedModelId: models.selectedModelId,
    selectedDatasetIds: dataState.selectedDatasetIds,
  });
  const artifacts = useArtifacts(runStream.run);

  async function createRun() {
    setActiveModule("run");
    try {
      await runStream.createRun();
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : String(err));
    }
  }

  async function openHistoricalRun(runId: string) {
    try {
      const historicalRun = await fetchRun(runId, projects.selectedProjectId || undefined);
      runStream.setRun(historicalRun);
      setActiveModule("artifacts");
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : String(err));
    }
  }

  const moduleTitle = modules.find((item) => item.id === activeModule)?.label ?? "工作台";

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <BarChart3 size={22} />
          <span>DataX</span>
        </div>

        <nav className="nav-section" aria-label="主功能">
          <div className="section-label">功能模块</div>
          {modules.map((item) => {
            const Icon = item.icon;
            return (
              <button
                className={`nav-button ${activeModule === item.id ? "active" : ""}`}
                data-testid={`module-${item.id}`}
                key={item.id}
                onClick={() => setActiveModule(item.id)}
                type="button"
              >
                <Icon size={16} />
                {item.label}
              </button>
            );
          })}
        </nav>

        <section className="nav-section sidebar-system-section">
          <button
            className="nav-button"
            onClick={() => setShowSystemInfo(!showSystemInfo)}
            type="button"
          >
            <Settings size={16} />
            系统设置
          </button>
          {showSystemInfo && (
            <SystemSettingsPanel
              models={models.models}
              selectedModelId={models.selectedModelId}
              setModels={models.setModels}
              setSelectedModelId={models.setSelectedModelId}
              skills={projects.skills}
            />
          )}
        </section>
      </aside>

      <section className="workbench">
        <header className="topbar">
          <div>
            <h1>{moduleTitle}</h1>
            <p>
              {projects.selectedProject
                ? projects.selectedProject.name
                : "先创建或选择一个分析项目，再继续配置上下文和运行工作流。"}
            </p>
          </div>
        </header>

        {errorMessage && (
          <div
            style={{
              backgroundColor: "#dc2626",
              color: "white",
              padding: "10px 16px",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              borderRadius: 6,
              marginBottom: 12,
            }}
          >
            <span style={{ flex: 1 }}>{errorMessage}</span>
            <button
              onClick={() => setErrorMessage("")}
              type="button"
              style={{
                background: "none",
                border: "none",
                color: "white",
                cursor: "pointer",
                padding: 4,
              }}
            >
              <X size={16} />
            </button>
          </div>
        )}

        {activeModule === "projects" && (
          <ProjectModule
            archiveProject={projects.archiveProject}
            createProject={projects.createProject}
            isSavingProject={projects.isSavingProject}
            newProjectDraft={projects.newProjectDraft}
            projectDraft={projects.projectDraft}
            projects={projects.projects}
            saveProject={projects.saveProject}
            selectedProject={projects.selectedProject}
            selectedProjectId={projects.selectedProjectId}
            setNewProjectDraft={projects.setNewProjectDraft}
            setProjectDraft={projects.setProjectDraft}
            setSelectedProjectId={projects.setSelectedProjectId}
          />
        )}

        {activeModule === "data" && (
          <DataModule
            datasets={dataState.datasets}
            uploadDataset={dataState.uploadDataset}
          />
        )}

        {activeModule === "context" && (
          <ContextModule
            contextDraft={projects.contextDraft}
            contexts={projects.contexts}
            deleteContext={projects.deleteContext}
            editContext={projects.editContext}
            editingContextId={projects.editingContextId}
            isSavingContext={projects.isSavingContext}
            saveContext={projects.saveContext}
            selectedProject={projects.selectedProject}
            selectedProjectId={projects.selectedProjectId}
            setContextDraft={projects.setContextDraft}
            setEditingContextId={projects.setEditingContextId}
          />
        )}

        {activeModule === "semantic-layer" && (
          <SemanticLayerModule
            layer={semantic.semanticLayer}
            selectedProjectName={projects.selectedProject?.name}
            selectedProjectId={projects.selectedProjectId}
            datasets={dataState.datasets}
            onSemanticLayerChange={semantic.onSemanticLayerChange}
          />
        )}

        {activeModule === "run" && (
          <RunModule
            contexts={projects.contexts}
            createRun={createRun}
            datasets={dataState.datasets}
            generatedCodeExecution={models.generatedCodeExecution}
            isRunning={runStream.isRunning}
            models={models.models}
            projects={projects.projects}
            question={runStream.question}
            run={runStream.run}
            runEvents={runStream.runEvents}
            selectedContextIds={projects.selectedContextIds}
            selectedDatasetIds={dataState.selectedDatasetIds}
            selectedModelId={models.selectedModelId}
            selectedProject={projects.selectedProject}
            selectedProjectId={projects.selectedProjectId}
            selectedSkill={runStream.selectedSkill}
            semanticLayer={semantic.semanticLayer}
            setQuestion={runStream.setQuestion}
            setSelectedModelId={models.setSelectedModelId}
            setSelectedProjectId={projects.setSelectedProjectId}
            setSelectedSkill={runStream.setSelectedSkill}
            skills={projects.skills}
            toggleContext={projects.toggleContext}
            toggleDataset={dataState.toggleDataset}
          />
        )}

        {activeModule === "artifacts" && (
          <ArtifactModule
            activeArtifact={artifacts.activeArtifact}
            activeArtifactId={artifacts.activeArtifactId}
            onOpenRun={openHistoricalRun}
            run={runStream.run}
            selectedProjectId={projects.selectedProjectId}
            setActiveArtifactId={artifacts.setActiveArtifactId}
          />
        )}

        {activeModule === "trace" && (
          <TraceModule
            currentRun={runStream.run}
            onOpenRun={openHistoricalRun}
            selectedProjectId={projects.selectedProjectId}
          />
        )}
      </section>
    </main>
  );
}
