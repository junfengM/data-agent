import type { ChartData, JsonRecord } from "../types";

/** Build chart data for Recharts from manifest chart + dataset rows. */
export function buildChartData(
  chart: Record<string, unknown>,
  rows: Array<Record<string, unknown>>,
): ChartData {
  const encodings = (chart.encodings || {}) as Record<string, Record<string, unknown>>;
  const xEnc = encodings.x || {};
  const yEnc = encodings.y || {};
  const xFields = Array.isArray(xEnc.fields) ? xEnc.fields : [];
  const yFields = Array.isArray(yEnc.fields) ? yEnc.fields : [];
  const xField = xEnc.field || xFields[0];
  const yField = yEnc.field || yFields[0];
  const chartType = String(chart.type || "bar");
  const sizeField = encodings.size?.field;
  const colorField = encodings.color?.field;
  const labelField = encodings.label?.field;

  const getSecondaryValue = (row: Record<string, unknown>): number | undefined => {
    if (yFields.length > 1) {
      const secondYField = String(yFields[1]);
      if (row[secondYField] !== undefined) {
        return Number(row[secondYField]) || 0;
      }
    }
    if (chartType === "scatter" && sizeField && row[sizeField as string] !== undefined) {
      return Number(row[sizeField as string]) || 0;
    }
    return undefined;
  };

  return {
    chart_type: chartType,
    unit: String(chart.unit || yEnc.unit || ""),
    source: String(chart.source_id || ""),
    description: String(chart.subtitle || chart.description || ""),
    x_axis_title: String(chart.x_axis_title || xEnc.label || xField || ""),
    y_axis_title: String(chart.y_axis_title || yEnc.label || yField || ""),
    rows: rows.map((row) => {
      const secondary = getSecondaryValue(row);
      const base: Record<string, unknown> = {
        label: String(row[labelField as string] ?? row[xField] ?? ""),
        value: Number(row[yField]) || 0,
      };
      if (chartType === "scatter") {
        base.x_value = Number(row[xField]) || 0;
      }
      if (secondary !== undefined) {
        base.secondary_value = secondary;
      }
      for (const statField of ["min", "q1", "q3", "max"]) {
        if (row[statField] !== undefined) {
          base[statField] = row[statField];
        }
      }
      if (colorField) {
        base.color = row[colorField as string];
      }
      return base as unknown as ChartData["rows"][number];
    }),
  };
}

export function chooseRenderableChartType(chartType: string, rowCount: number): string {
  if ((chartType === "line" || chartType === "area") && rowCount < 6) {
    return "column";
  }
  if (chartType === "scatter" && rowCount < 8) {
    return "horizontalBar";
  }
  if (chartType === "pie" && rowCount > 5) {
    return "horizontalBar";
  }
  return chartType;
}

export function formatCompactNumber(value: number, unit = ""): string {
  if (!Number.isFinite(value)) return "-";

  const absolute = Math.abs(value);
  let scaled = value;
  let suffix = "";
  if (absolute >= 100_000_000) {
    scaled = value / 100_000_000;
    suffix = "亿";
  } else if (absolute >= 10_000) {
    scaled = value / 10_000;
    suffix = "万";
  }

  const digits = Math.abs(scaled) >= 100 || Number.isInteger(scaled) ? 0 : 1;
  const formatted = scaled.toLocaleString("zh-CN", {
    minimumFractionDigits: 0,
    maximumFractionDigits: digits,
  });
  const normalizedUnit = unit.trim();
  if (["¥", "￥", "$"].includes(normalizedUnit)) {
    return `${normalizedUnit}${formatted}${suffix}`;
  }
  return `${formatted}${suffix}${normalizedUnit}`;
}

/** Build heatmap rawData from manifest chart + dataset rows. */
export function buildHeatmapRawData(
  chart: Record<string, unknown>,
  rows: Array<Record<string, unknown>>,
): JsonRecord | undefined {
  const chartType = String(chart.type || "bar");
  if (chartType !== "heatmap") return undefined;

  const encodings = (chart.encodings || {}) as Record<string, Record<string, unknown>>;
  const yEnc = encodings.y || {};
  const xEnc = encodings.x || {};
  const yFields = Array.isArray(yEnc.fields) ? yEnc.fields : [];
  const xFields = Array.isArray(xEnc.fields) ? xEnc.fields : [];
  const xField = xEnc.field || xFields[0];
  const yField = yEnc.field || yFields[0];

  const valueField = String(
    (yFields.length > 1 ? yFields[1] : undefined)
    || encodings.matrix?.field
    || encodings.value?.field
    || encodings.color?.field
    || "value",
  );

  return {
    rows: (valueField !== "value"
      ? rows.map((r) => ({ ...r, value: r[valueField] }))
      : rows) as JsonRecord[],
    x: String(encodings.x?.field || xField),
    y: String(encodings.y?.field || yField),
  };
}

/** Quick validation: does chart metadata have required fields for rendering? */
export function validateChartMetadata(chart: Record<string, unknown>): {
  valid: boolean;
  issues: string[];
} {
  const issues: string[] = [];
  if (!chart.type) issues.push("missing chart type");
  if (!chart.dataset) issues.push("missing dataset key");
  return { valid: issues.length === 0, issues };
}
