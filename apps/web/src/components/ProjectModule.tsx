import React from "react";
import { Archive, Plus, Save } from "lucide-react";
import type { AnalysisProject } from "../types";
import { EmptyState, PanelHeader } from "../shared";

type Props = {
  archiveProject: () => Promise<void>;
  createProject: () => Promise<void>;
  isSavingProject: boolean;
  newProjectDraft: { name: string; description: string };
  projectDraft: { name: string; description: string };
  projects: AnalysisProject[];
  saveProject: () => Promise<void>;
  selectedProject?: AnalysisProject;
  selectedProjectId: string;
  setNewProjectDraft: React.Dispatch<React.SetStateAction<{ name: string; description: string }>>;
  setProjectDraft: React.Dispatch<React.SetStateAction<{ name: string; description: string }>>;
  setSelectedProjectId: React.Dispatch<React.SetStateAction<string>>;
};

export default function ProjectModule(props: Props) {
  const [isCreating, setIsCreating] = React.useState(false);
  const activeDraft = isCreating ? props.newProjectDraft : props.projectDraft;
  const setActiveDraft = isCreating ? props.setNewProjectDraft : props.setProjectDraft;
  const canEditSelectedProject = Boolean(props.selectedProjectId);

  function startCreating() {
    props.setNewProjectDraft({ name: "", description: "" });
    setIsCreating(true);
  }

  function selectProject(projectId: string) {
    setIsCreating(false);
    props.setSelectedProjectId(projectId);
  }

  function cancelCreating() {
    props.setNewProjectDraft({ name: "", description: "" });
    setIsCreating(false);
  }

  async function submitNewProject() {
    if (!props.newProjectDraft.name.trim()) return;
    await props.createProject();
    setIsCreating(false);
  }

  return (
    <div className="module-grid two-columns">
      <section className="panel">
        <PanelHeader title="项目列表" subtitle="每个分析项目都有独立的背景、指标定义和运行历史。" />
        <button className="secondary-button" onClick={startCreating} type="button">
          <Plus size={16} />
          新建项目
        </button>
        <div className="project-list large">
          {props.projects.length ? (
            props.projects.map((project) => (
              <button
                className={`project-button light ${!isCreating && props.selectedProjectId === project.id ? "selected" : ""}`}
                key={project.id}
                onClick={() => selectProject(project.id)}
                type="button"
              >
                <span>{project.name}</span>
                <small>{project.description || project.status}</small>
              </button>
            ))
          ) : (
            <EmptyState text="还没有项目。点击上方新建一个分析项目。" />
          )}
        </div>
      </section>

      <section className="panel">
        <PanelHeader
          title={isCreating ? "新建项目" : "项目资料"}
          subtitle={
            isCreating
              ? "按业务主题、产品线或固定报告场景创建项目。"
              : "保存项目级背景，运行分析时会自动进入报告上下文。"
          }
        />
        <div className="field-row">
          <label htmlFor={isCreating ? "new-project-name" : "project-name"}>项目名称</label>
          <input
            disabled={!isCreating && !canEditSelectedProject}
            id={isCreating ? "new-project-name" : "project-name"}
            onChange={(event) =>
              setActiveDraft((current) => ({ ...current, name: event.target.value }))
            }
            placeholder={isCreating ? "例如：会员增长周报" : "请选择或新建项目"}
            value={activeDraft.name}
          />
        </div>
        <div className="field-row">
          <label htmlFor={isCreating ? "new-project-description" : "project-description"}>项目背景</label>
          <textarea
            disabled={!isCreating && !canEditSelectedProject}
            id={isCreating ? "new-project-description" : "project-description"}
            onChange={(event) =>
              setActiveDraft((current) => ({ ...current, description: event.target.value }))
            }
            placeholder="保存这个项目的业务背景、目标、常用分析边界。运行分析时会自动进入报告上下文。"
            value={activeDraft.description}
          />
        </div>

        {isCreating ? (
          <div className="button-row compact">
            <button
              className="secondary-button"
              disabled={!props.newProjectDraft.name.trim()}
              onClick={submitNewProject}
              type="button"
            >
              <Plus size={16} />
              创建项目
            </button>
            <button className="ghost-button" onClick={cancelCreating} type="button">
              取消
            </button>
          </div>
        ) : (
          <div className="button-row compact">
            <button
              className="secondary-button"
              disabled={!props.selectedProjectId || props.isSavingProject}
              onClick={props.saveProject}
              type="button"
            >
              <Save size={16} />
              保存项目
            </button>
            <button
              className="ghost-button"
              disabled={!props.selectedProjectId}
              onClick={props.archiveProject}
              type="button"
            >
              <Archive size={16} />
              归档
            </button>
          </div>
        )}
      </section>
    </div>
  );
}
