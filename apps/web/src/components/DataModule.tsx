import React from "react";
import { FileUp } from "lucide-react";
import type { Dataset } from "../types";
import { EmptyState, PanelHeader } from "../shared";

type Props = {
  datasets: Dataset[];
  uploadDataset: (file: File | null) => Promise<void>;
};

export default function DataModule(props: Props) {
  return (
    <div className="module-grid two-columns">
      <section className="panel">
        <PanelHeader title="上传数据" subtitle="当前 MVP 支持 CSV、XLSX、XLS 文件。" />
        <label className="upload-dropzone">
          <FileUp size={28} />
          <span>选择本地 CSV/XLSX 文件</span>
          <input
            accept=".csv,.xlsx,.xls"
            onChange={(event) => props.uploadDataset(event.target.files?.[0] ?? null)}
            type="file"
          />
        </label>
      </section>

      <section className="panel">
        <PanelHeader title="数据集资产" subtitle={`${props.datasets.length} 个可用数据集；本次运行使用哪些数据，请到「分析运行」中选择。`} />
        <div className="dataset-list large">
          {props.datasets.length ? (
            props.datasets.map((dataset) => (
              <div className="dataset-row light" key={dataset.id} title={dataset.path}>
                <span>{dataset.filename}</span>
                <small>{[dataset.created_at ?? "本地文件", dataset.project_id ? "项目数据" : "共享数据"].join(" · ")}</small>
              </div>
            ))
          ) : (
            <EmptyState text="还没有上传数据集。" />
          )}
        </div>
      </section>
    </div>
  );
}
