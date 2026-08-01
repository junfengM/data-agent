import React from "react";
import { FileUp } from "lucide-react";
import type { Dataset } from "../types";
import { EmptyState, PanelHeader } from "../shared";

type Props = {
  datasets: Dataset[];
  onNotify?: (message: string, kind?: "error" | "success") => void;
  uploadDataset: (file: File | null) => Promise<boolean>;
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
            onChange={(event) => {
              const file = event.target.files?.[0] ?? null;
              void props.uploadDataset(file).then((ok) => {
                if (ok) props.onNotify?.("数据集上传成功。", "success");
              });
            }}
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
            <EmptyState text="还没有上传数据集。" hint="选择 CSV/XLSX 文件上传后，即可到「分析运行」开始分析。" />
          )}
        </div>
      </section>
    </div>
  );
}
