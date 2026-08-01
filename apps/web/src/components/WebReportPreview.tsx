import { FileCode } from "lucide-react";

import type { Artifact } from "../types";
import { apiFetch, resolveApiUrl } from "../apiClient";
import { downloadBlob, safeFilename } from "../utils/download";
import { EmptyState, WidgetHeader } from "../shared";

export function isWebReportArtifact(
  artifact: Pick<Artifact, "title" | "type" | "data">,
) {
  return (
    artifact.title === "网页版报告" ||
    artifact.data?.renderer === "delivery_renderer_v0" ||
    artifact.data?.renderer === "quarto_html" ||
    (artifact.type === "html_report" && artifact.data?.renderer === "quarto_html")
  );
}

export function webReportAssetUrl(
  artifact: Pick<Artifact, "path">,
  runId?: string,
) {
  const filename = artifact.path
    ? artifact.path.split(/[\\/]/).pop() || ""
    : "";
  return runId && filename
    ? resolveApiUrl(`/api/runs/${runId}/assets/${encodeURIComponent(filename)}`)
    : "";
}

export function WebReportPreviewWidget({
  artifact,
  runId,
}: {
  artifact: Artifact;
  runId: string;
}) {
  const assetUrl = webReportAssetUrl(artifact, runId);

  async function handleDownloadHtml() {
    if (!assetUrl) return;
    try {
      const response = await apiFetch(assetUrl);
      if (!response.ok) throw new Error("下载失败");
      const blob = await response.blob();
      downloadBlob(blob, `${safeFilename(artifact.title || "web-report")}.html`);
    } catch (error) {
      alert(error instanceof Error ? error.message : "下载 HTML 失败");
    }
  }

  if (!assetUrl) {
    return (
      <article className="artifact-widget">
        <WidgetHeader artifact={artifact} />
        <EmptyState text="网页版报告缺少可预览的 HTML 文件。" />
      </article>
    );
  }

  return (
    <article className="artifact-widget web-report-widget">
      <div className="report-actionbar web-report-actionbar">
        <WidgetHeader artifact={artifact} />
        <button
          className="ghost-button export-button"
          onClick={handleDownloadHtml}
          type="button"
        >
          <FileCode size={16} /> 下载 HTML
        </button>
      </div>
      <div className="web-report-preview-shell">
        <iframe
          className="web-report-preview-frame"
          loading="lazy"
          sandbox="allow-scripts"
          src={assetUrl}
          title={artifact.title || "网页版报告"}
        />
      </div>
    </article>
  );
}
