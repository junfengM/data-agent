import React from "react";
import { Database } from "lucide-react";
import { formatCell } from "../shared";
import { humanizeReportLabel } from "../utils/reportLayout";

type Row = Record<string, unknown>;

type EvidenceDetailsProps = {
  block?: Row;
  item?: Row;
  rows?: Row[];
  columns?: Array<{ field: string; label: string }>;
  sources?: Row[];
  evidenceMap?: Row[];
};

export function ArtifactEvidenceDetails({
  block,
  item,
  rows = [],
  columns,
  sources = [],
  evidenceMap = [],
}: EvidenceDetailsProps) {
  const evidenceIds = extractStringList(block?.evidence_ids ?? block?.evidenceIds);
  const sourceIds = [block?.source_id, item?.source_id]
    .map((value) => String(value || ""))
    .filter(Boolean);
  const linkedEvidence = evidenceIds
    .map((id) => evidenceMap.find((entry) => String(entry.id) === id) || { id })
    .filter(Boolean);
  const linkedSources = sources.filter((source) => sourceIds.includes(String(source.id)));

  // Only explicit dataset rows should appear in the evidence table preview.
  // Visual-deck blocks also carry small inline `items` arrays for rendering cards,
  // rankings, and action lists. Showing those inline items again as "数据预览"
  // makes the report noisy and creates the impression that every card is a table.
  const resolvedRows = rows.length ? rows : [];
  const previewRows = resolvedRows.slice(0, 8);
  const previewColumns = resolveColumns(columns, previewRows);

  if (!linkedEvidence.length && !linkedSources.length && !previewRows.length) {
    return null;
  }

  return (
    <details className="artifact-evidence-details">
      <summary><Database size={13} /> 数据依据</summary>
      <div className="artifact-evidence-grid">
        {linkedEvidence.length > 0 && (
          <section className="artifact-evidence-panel">
            <h5>证据</h5>
            <ul className="artifact-evidence-mini-list">
              {linkedEvidence.map((entry, index) => (
                <li key={`${String(entry.id || "evidence")}-${index}`}>
                  <strong>{String(entry.title || entry.id || "证据")}</strong>
                  {entry.type ? <span>{String(entry.type)}</span> : null}
                  {entry.source_dataset ? <small>来源：{String(entry.source_dataset)}</small> : null}
                  {entry.row_count != null ? <small>{String(entry.row_count)} 行</small> : null}
                </li>
              ))}
            </ul>
          </section>
        )}

        {linkedSources.length > 0 && (
          <section className="artifact-evidence-panel">
            <h5>来源</h5>
            <ul className="artifact-evidence-mini-list">
              {linkedSources.map((source, index) => {
                const query = isRecord(source.query) ? source.query : undefined;
                return (
                  <li key={`${String(source.id || "source")}-${index}`}>
                    <strong>{String(source.label || source.id || "数据来源")}</strong>
                    {source.path ? <small>{String(source.path)}</small> : null}
                    {query?.description ? <small>{String(query.description)}</small> : null}
                  </li>
                );
              })}
            </ul>
          </section>
        )}

        {previewRows.length > 0 && previewColumns.length > 0 && (
          <section className="artifact-evidence-panel artifact-evidence-data-panel">
            <h5>数据预览</h5>
            <div className="artifact-evidence-table-scroll">
              <table>
                <thead>
                  <tr>
                    {previewColumns.map((column) => <th key={column.field}>{column.label}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {previewRows.map((row, rowIndex) => (
                    <tr key={rowIndex}>
                      {previewColumns.map((column) => <td key={column.field}>{formatCell(row[column.field])}</td>)}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <small className="artifact-evidence-row-note">显示前 {previewRows.length} 行，共 {resolvedRows.length} 行可用数据。</small>
          </section>
        )}
      </div>
    </details>
  );
}

function extractStringList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.map((item) => String(item || "")).filter(Boolean);
}

function resolveColumns(columns: Array<{ field: string; label: string }> | undefined, rows: Row[]) {
  if (columns && columns.length) return columns.filter((column) => column.field);
  const first = rows.find(isRecord);
  if (!first) return [];
  return Object.keys(first).slice(0, 8).map((key) => ({ field: key, label: humanizeReportLabel(key) }));
}

function isRecord(value: unknown): value is Row {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
