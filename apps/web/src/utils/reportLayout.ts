const SUMMARY_HEADING = /^(#{1,4})\s*(执行摘要|核心结论|摘要|executive summary|summary)\b/im;

const TECHNICAL_LABELS: Record<string, string> = {
  aov: "客单价",
  avg_order_value: "客单价",
  average_order_value: "客单价",
  category: "品类",
  category_monthly: "品类月度表现",
  category_totals: "品类汇总",
  chart_aov_comparison: "品类客单价对比",
  chart_category_composition: "品类月度构成",
  chart_category_growth: "品类增长对比",
  chart_category_share: "品类营收占比",
  chart_monthly_revenue_trend: "月度营收表现",
  month: "月份",
  month_sort: "月份序号",
  monthly_trend: "月度核心指标",
  order_share_pct: "订单占比",
  orders: "订单数",
  orders_growth_pct: "订单环比",
  product: "产品",
  product_totals: "产品汇总",
  revenue: "营收",
  revenue_growth_pct: "营收环比",
  revenue_share_pct: "营收占比",
  total_orders: "总订单",
  total_revenue: "总营收",
};

const STRUCTURAL_VISUAL_TYPES = new Set([
  "executive_storyboard",
  "adaptive_story",
  "kpi_grid",
  "delta_bridge",
  "leaderboard_pair",
  "trend_panel",
  "composition_panel",
  "forecast_band",
  "decision_matrix",
  "data_quality_panel",
  "metric_change",
  "stage_timeline",
  "comparison_grid",
]);

export function prepareReportBlocks(
  blocks: Array<Record<string, unknown>>,
  reportTitle: string,
): Array<Record<string, unknown>> {
  // When blocks carry renderer_target, the backend's compose_reading_flow()
  // has already produced the final ordering. Frontend only sanitizes markdown.
  const isLayerAware = blocks.some((block) => block.renderer_target != null);

  if (isLayerAware) {
    return blocks.map((block) => {
      if (String(block.type || "") === "markdown") {
        const body = sanitizeReportMarkdown(stripDuplicateReportTitle(String(block.body || ""), reportTitle));
        return body.trim() ? { ...block, body } : null;
      }
      return block;
    }).filter((block): block is Record<string, unknown> => block != null);
  }

  // Legacy path: no renderer_target — frontend must reorder.
  const hasNarrative = blocks.filter((block) => String(block.type || "") === "markdown").length >= 2;
  const leadingVisuals: Array<Record<string, unknown>> = [];
  const readingFlow: Array<Record<string, unknown>> = [];
  let reachedNarrative = false;

  for (const block of blocks) {
    const type = String(block.type || "");
    if (!reachedNarrative && type !== "markdown") {
      if (STRUCTURAL_VISUAL_TYPES.has(type)) {
        if (isUsefulStructuralVisual(block)) leadingVisuals.push(block);
        continue;
      }
    }

    if (type === "markdown") {
      reachedNarrative = true;
      const body = sanitizeReportMarkdown(stripDuplicateReportTitle(String(block.body || ""), reportTitle));
      if (!body.trim()) continue;
      readingFlow.push({ ...block, body });
      continue;
    }
    readingFlow.push(block);
  }

  if (!leadingVisuals.length) return readingFlow;
  const summaryIndex = readingFlow.findIndex((block) =>
    String(block.type || "") === "markdown" && SUMMARY_HEADING.test(String(block.body || "")),
  );
  const firstNarrativeIndex = readingFlow.findIndex((block) => String(block.type || "") === "markdown");
  const insertAt = summaryIndex >= 0 ? summaryIndex + 1 : Math.max(firstNarrativeIndex + 1, 0);
  return [...readingFlow.slice(0, insertAt), ...leadingVisuals, ...readingFlow.slice(insertAt)];
}

export function stripDuplicateReportTitle(markdown: string, reportTitle: string): string {
  const lines = markdown.split("\n");
  const firstContentIndex = lines.findIndex((line) => line.trim());
  if (firstContentIndex < 0) return markdown;
  const match = lines[firstContentIndex].match(/^#\s+(.+?)\s*$/);
  if (!match || normalizeText(match[1]) !== normalizeText(reportTitle)) return markdown;
  lines.splice(firstContentIndex, 1);
  return lines.join("\n").replace(/^\s+/, "");
}

export function humanizeReportLabel(value: string): string {
  const trimmed = value.trim();
  if (!trimmed) return "";
  const key = trimmed.toLowerCase().replace(/\.(html|png|jpg|jpeg|svg)$/i, "");
  if (TECHNICAL_LABELS[key]) return TECHNICAL_LABELS[key];
  if (/[\u3400-\u9fff]/.test(trimmed) || !/[_-]/.test(trimmed)) return trimmed;
  return trimmed
    .replace(/\.(html|png|jpg|jpeg|svg)$/i, "")
    .split(/[_-]+/)
    .filter(Boolean)
    .map((part) => TECHNICAL_LABELS[part.toLowerCase()] || part)
    .join(" · ");
}

function sanitizeReportMarkdown(markdown: string): string {
  return markdown
    .split("\n")
    .filter((line) => !/\[[^\]]+\]\([^)]*\.(html|png|jpe?g|svg)\)/i.test(line))
    .join("\n")
    .replace(/\bElectronics\b/g, "电子")
    .replace(/\bClothing\b/g, "服装")
    .replace(/\bFood\b/g, "食品")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function isUsefulStructuralVisual(block: Record<string, unknown>): boolean {
  if (String(block.type || "") !== "leaderboard_pair") return true;
  const items = [...toRecordList(block.positive), ...toRecordList(block.negative)];
  if (items.length < 2) return items.length > 0;
  const labels = items.map((item) => String(item.label ?? item.name ?? item.dimension ?? "")).filter(Boolean);
  const uniqueRatio = new Set(labels).size / Math.max(labels.length, 1);
  return uniqueRatio >= 0.75;
}

function toRecordList(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value)
    ? value.filter((item): item is Record<string, unknown> => typeof item === "object" && item !== null && !Array.isArray(item))
    : [];
}

function normalizeText(value: string): string {
  return value.trim().replace(/\s+/g, " ").toLowerCase();
}
