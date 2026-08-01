import React from "react";
import { Pencil, Plus, Trash2 } from "lucide-react";
import type { AnalysisProject, ProjectContext } from "../types";
import { contextKindLabels, emptyContextForm, EmptyState, PanelHeader } from "../shared";

type Props = {
  contextDraft: typeof emptyContextForm;
  contexts: ProjectContext[];
  deleteContext: (contextId: string) => Promise<void>;
  editContext: (context: ProjectContext) => void;
  editingContextId: string;
  isSavingContext: boolean;
  saveContext: () => Promise<void>;
  selectedProject?: AnalysisProject;
  selectedProjectId: string;
  setContextDraft: React.Dispatch<React.SetStateAction<typeof emptyContextForm>>;
  setEditingContextId: React.Dispatch<React.SetStateAction<string>>;
};

export default function ContextModule(props: Props) {
  return (
    <div className="module-grid two-columns">
      <section className="panel">
        <PanelHeader title="上下文包" subtitle="这些条目只属于当前项目，不会变成全局背景。" />
        <div className="context-list roomy">
          {props.contexts.length ? (
            props.contexts.map((context) => (
              <div className="context-row" key={context.id}>
                <button onClick={() => props.editContext(context)} type="button">
                  <strong>{context.title}</strong>
                  <span>{contextKindLabels[context.kind] ?? context.kind}</span>
                  <small>{context.body.slice(0, 90)}{context.body.length > 90 ? "…" : ""}</small>
                </button>
                <button
                  className="icon-button danger"
                  onClick={() => props.deleteContext(context.id)}
                  title="删除上下文"
                  type="button"
                >
                  <Trash2 size={15} />
                </button>
              </div>
            ))
          ) : (
            <EmptyState text={props.selectedProject ? "这个项目还没有上下文。" : "请先选择或创建项目。"} />
          )}
        </div>
      </section>

      <section className="panel">
        <PanelHeader
          title={props.editingContextId ? "编辑上下文" : "新增上下文"}
          subtitle="可维护业务背景、指标定义、报告偏好、已知数据问题和受众。"
        />
        <div className="field-row">
          <label htmlFor="context-kind">类型</label>
          <select
            disabled={!props.selectedProjectId}
            id="context-kind"
            onChange={(event) =>
              props.setContextDraft((current) => ({ ...current, kind: event.target.value }))
            }
            value={props.contextDraft.kind}
          >
            {Object.entries(contextKindLabels).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </div>
        <div className="field-row">
          <label htmlFor="context-title">标题</label>
          <input
            disabled={!props.selectedProjectId}
            id="context-title"
            onChange={(event) =>
              props.setContextDraft((current) => ({ ...current, title: event.target.value }))
            }
            value={props.contextDraft.title}
          />
        </div>
        <div className="field-row">
          <label htmlFor="context-body">内容</label>
          <textarea
            disabled={!props.selectedProjectId}
            id="context-body"
            onChange={(event) =>
              props.setContextDraft((current) => ({ ...current, body: event.target.value }))
            }
            value={props.contextDraft.body}
          />
        </div>
        <div className="button-row compact">
          <button
            className="secondary-button"
            disabled={!props.selectedProjectId || props.isSavingContext}
            onClick={props.saveContext}
            type="button"
          >
            {props.editingContextId ? <Pencil size={16} /> : <Plus size={16} />}
            {props.editingContextId ? "更新上下文" : "添加上下文"}
          </button>
          <button
            className="ghost-button"
            onClick={() => {
              props.setEditingContextId("");
              props.setContextDraft(emptyContextForm);
            }}
            type="button"
          >
            清空
          </button>
        </div>
      </section>
    </div>
  );
}
