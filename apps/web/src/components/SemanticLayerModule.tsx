import { useState } from "react";
import { Layers, Sparkles, Check, X, Loader2 } from "lucide-react";
import { apiFetch } from "../apiClient";
import type { SemanticLayerMeta } from "../types";
import { EmptyState, PanelHeader } from "../shared";

type Props = {
  layer: SemanticLayerMeta | null;
  selectedProjectName?: string;
  selectedProjectId?: string;
  datasets?: Array<{ id: string; filename: string }>;
  onSemanticLayerChange?: (layer: SemanticLayerMeta | null) => void;
};

export default function SemanticLayerModule({
  layer,
  selectedProjectName,
  selectedProjectId,
  datasets,
  onSemanticLayerChange,
}: Props) {
  const metrics = layer?.metrics || [];
  const dimensions = layer?.dimensions || [];
  const [selectedDatasetId, setSelectedDatasetId] = useState("");
  const [drafting, setDrafting] = useState(false);
  const [draftResult, setDraftResult] = useState<any>(null);
  const [draftError, setDraftError] = useState("");
  const [saving, setSaving] = useState(false);

  const handleGenerateDraft = async () => {
    if (!selectedProjectId || !selectedDatasetId) return;
    setDrafting(true);
    setDraftError("");
    setDraftResult(null);
    try {
      const resp = await apiFetch(
        `/api/projects/${selectedProjectId}/datasets/${selectedDatasetId}/semantic-draft`,
        { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" }
      );
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: resp.statusText }));
        throw new Error(err.detail || "生成失败");
      }
      const draft = await resp.json();
      setDraftResult(draft);
    } catch (e: any) {
      setDraftError(e.message);
    } finally {
      setDrafting(false);
    }
  };

  const handleSaveDraft = async () => {
    if (!selectedProjectId || !draftResult) return;
    setSaving(true);
    try {
      const resp = await apiFetch(
        `/api/projects/${selectedProjectId}/semantic-drafts/${draftResult.id}/confirm`,
        { method: "POST" }
      );
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || "保存失败");
      // Reload active semantic layer after confirm
      const slResp = await apiFetch(`/api/projects/${selectedProjectId}/semantic-layers/active`);
      if (slResp.ok) {
        onSemanticLayerChange?.(await slResp.json());
      }
      setDraftResult(null);
    } catch (e: any) {
      setDraftError(e.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="module-grid">
      <section className="panel wide semantic-layer-page">
        <PanelHeader
          title="语义层"
          subtitle="当前项目激活的指标、维度和口径定义。"
        />

        {selectedProjectId && datasets && datasets.length > 0 && (
          <div className="sl-draft-controls">
            <select
              value={selectedDatasetId}
              onChange={(e) => setSelectedDatasetId(e.target.value)}
              className="sl-dataset-select"
            >
              <option value="">选择数据集...</option>
              {datasets.map((d) => (
                <option key={d.id} value={d.id}>{d.filename}</option>
              ))}
            </select>
            <button
              className="secondary-button"
              disabled={!selectedDatasetId || drafting}
              onClick={handleGenerateDraft}
              type="button"
            >
              {drafting ? <Loader2 size={16} className="spin" /> : <Sparkles size={16} />}
              {drafting ? "生成中..." : "生成语义层草案"}
            </button>
          </div>
        )}

        {draftError && <div className="error-banner">{draftError}</div>}

        {draftResult && (
          <div className="sl-draft-preview">
            <h4>草案预览</h4>
            <div className="sl-draft-stats">
              <span className="stat-badge">
                {draftResult.suggested_metrics?.length || 0} 个指标
              </span>
              <span className="stat-badge">
                {draftResult.columns?.filter((c: any) => c.role === "dimension").length || 0} 个维度
              </span>
            </div>
            {draftResult.suggested_metrics?.length > 0 && (
              <div className="semantic-layer-table-wrap">
                <table className="semantic-layer-table">
                  <thead>
                    <tr>
                      <th>指标名</th>
                      <th>公式</th>
                      <th>粒度</th>
                      <th>来源表</th>
                      <th>来源列</th>
                    </tr>
                  </thead>
                  <tbody>
                    {draftResult.suggested_metrics.map((m: any, i: number) => (
                      <tr key={i}>
                        <td className="sl-name">{m.name}</td>
                        <td><code className="semantic-formula-code">{m.formula}</code></td>
                        <td>{m.grain ? <span className="semantic-grain-pill">{m.grain}</span> : "—"}</td>
                        <td>{m.source_table || m.sheet_name || "—"}</td>
                        <td><code>{m.source_columns?.join(", ")}</code></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <div className="button-row">
              <button className="primary-button" onClick={handleSaveDraft} disabled={saving} type="button">
                {saving ? <Loader2 size={16} className="spin" /> : <Check size={16} />}
                保存并激活语义层
              </button>
              <button className="ghost-button" onClick={() => setDraftResult(null)} type="button">
                <X size={16} />取消
              </button>
            </div>
          </div>
        )}

        {!layer && !draftResult && (
          <EmptyState text={selectedProjectId ? "当前项目还没有激活的语义层。上传数据集后可生成草案。" : "请先选择项目。"} />
        )}

        {layer && (
          <>
            <div className="semantic-layer-summary">
              <div className="semantic-layer-stats">
                <span className="stat-badge">
                  <Layers size={16} />
                  {metrics.length} 个指标
                </span>
                <span className="stat-badge">{dimensions.length} 个维度</span>
              </div>
              {layer.path && <code className="semantic-layer-path">{layer.path}</code>}
            </div>

            {metrics.length > 0 ? (
              <div className="sl-section">
                <h4>指标定义（{metrics.length}）</h4>
                <div className="semantic-layer-table-wrap">
                  <table className="semantic-layer-table">
                    <thead>
                      <tr>
                        <th>指标名</th>
                        <th>公式 / 口径</th>
                        <th>粒度</th>
                        <th>注意事项</th>
                      </tr>
                    </thead>
                    <tbody>
                      {metrics.map((m, i) => (
                        <tr key={i}>
                          <td className="sl-name">{m.name}</td>
                          <td><code className="semantic-formula-code">{m.formula}</code></td>
                          <td>{m.grain ? <span className="semantic-grain-pill">{m.grain}</span> : "—"}</td>
                          <td className="semantic-muted">{m.caveat || "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ) : (
              <div className="sl-section">
                <h4>指标定义</h4>
                <EmptyState text="尚无指标定义。" />
              </div>
            )}

            {dimensions.length > 0 ? (
              <div className="sl-section">
                <h4>维度定义（{dimensions.length}）</h4>
                <div className="semantic-layer-table-wrap">
                  <table className="semantic-layer-table">
                    <thead>
                      <tr>
                        <th>维度名</th>
                        <th>来源表</th>
                        <th>来源字段</th>
                      </tr>
                    </thead>
                    <tbody>
                      {dimensions.map((d, i) => (
                        <tr key={i}>
                          <td className="sl-name">{d.name}</td>
                          <td>{d.source_table || "—"}</td>
                          <td><code>{d.source_column}</code></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ) : (
              <div className="sl-section">
                <h4>维度定义</h4>
                <EmptyState text="尚无维度定义。" />
              </div>
            )}
          </>
        )}
      </section>
    </div>
  );
}
