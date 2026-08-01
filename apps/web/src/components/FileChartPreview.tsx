import { ExternalLink } from "lucide-react";

import { resolveApiUrl } from "../apiClient";

export function FileChartPreview({
  path,
  runId,
  title,
}: {
  path: string;
  runId?: string;
  title: string;
}) {
  const filename = path.split(/[\\/]/).pop() || "";
  const extension = filename.split(".").pop()?.toLowerCase() || "";
  const assetUrl =
    runId && filename
      ? resolveApiUrl(`/api/runs/${runId}/assets/${encodeURIComponent(filename)}`)
      : "";

  if (assetUrl && ["png", "jpg", "jpeg", "svg"].includes(extension)) {
    return (
      <figure className="chart-file-preview">
        <img alt={title} loading="lazy" src={assetUrl} />
        <figcaption>{filename}</figcaption>
      </figure>
    );
  }
  if (assetUrl && extension === "html") {
    return (
      <figure className="chart-file-preview chart-file-preview--html">
        <iframe
          loading="lazy"
          referrerPolicy="no-referrer"
          sandbox="allow-scripts"
          src={assetUrl}
          title={title}
        />
        <a
          className="chart-original-link"
          href={assetUrl}
          rel="noreferrer"
          target="_blank"
          title="打开原始交互图表"
        >
          <ExternalLink size={14} />
          <span>原始图表</span>
        </a>
      </figure>
    );
  }
  return (
    <div className="chart-file-preview chart-file-preview--fallback">
      <p>图表文件暂时无法预览。</p>
      {filename ? <code>{filename}</code> : null}
    </div>
  );
}
