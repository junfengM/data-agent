import { describe, it, expect } from "vitest";
import {
  buildChartData,
  buildHeatmapRawData,
  chooseRenderableChartType,
  formatCompactNumber,
  validateChartMetadata,
} from "../src/utils/chartAdapters";

describe("buildChartData", () => {
  const rows = [
    { month: "2024-01", revenue: 120_000, orders: 45 },
    { month: "2024-02", revenue: 135_000, orders: 52 },
  ];

  it("produces single-series chart data", () => {
    const chart = {
      type: "bar",
      dataset: "ds1",
      encodings: { x: { field: "month" }, y: { field: "revenue" } },
    };
    const result = buildChartData(chart, rows);
    expect(result.chart_type).toBe("bar");
    expect(result.rows).toHaveLength(2);
    expect(result.rows[0].label).toBe("2024-01");
    expect(result.rows[0].value).toBe(120_000);
  });

  it("produces secondary_value from yFields[1]", () => {
    const chart = {
      type: "line",
      dataset: "ds1",
      encodings: {
        x: { field: "month" },
        y: { fields: ["revenue", "orders"] },
      },
    };
    const result = buildChartData(chart, rows);
    expect(result.rows[0].secondary_value).toBe(45);
    expect(result.rows[1].secondary_value).toBe(52);
  });

  it("scatter uses sizeField for secondary when no yFields[1]", () => {
    const chart = {
      type: "scatter",
      dataset: "ds1",
      encodings: {
        x: { field: "revenue" },
        y: { field: "orders" },
        size: { field: "revenue" },
      },
    };
    const result = buildChartData(chart, rows);
    expect(result.rows[0].secondary_value).toBe(120_000);
    expect(result.rows[0].x_value).toBe(120_000);
  });

  it("passes unit/source/description fields", () => {
    const chart = {
      type: "bar",
      dataset: "ds1",
      unit: "万元",
      description: "Monthly revenue",
      encodings: { x: { field: "month" }, y: { field: "revenue", unit: "元" } },
    };
    const result = buildChartData(chart, rows);
    expect(result.unit).toBe("万元");
    expect(result.source).toBe("");
    expect(result.description).toBe("Monthly revenue");
  });

  it("preserves boxPlot quartile fields", () => {
    const boxRows = [
      { category: "A", min: 10, q1: 20, q3: 60, max: 80 },
    ];
    const chart = {
      type: "boxPlot",
      dataset: "ds1",
      encodings: { x: { field: "category" }, y: { field: "q3" } },
    };
    const result = buildChartData(chart, boxRows);
    expect(result.rows[0].min).toBe(10);
    expect(result.rows[0].q1).toBe(20);
    expect(result.rows[0].q3).toBe(60);
    expect(result.rows[0].max).toBe(80);
  });

  it("preserves color field on rows", () => {
    const colorRows = [{ month: "Jan", val: 100, cat: "A" }];
    const chart = {
      type: "bar",
      dataset: "ds1",
      encodings: {
        x: { field: "month" },
        y: { field: "val" },
        color: { field: "cat" },
      },
    };
    const result = buildChartData(chart, colorRows);
    expect(result.rows[0].color).toBe("A");
  });
});

describe("chooseRenderableChartType", () => {
  it("uses columns for sparse time series", () => {
    expect(chooseRenderableChartType("line", 3)).toBe("column");
    expect(chooseRenderableChartType("area", 5)).toBe("column");
  });

  it("keeps sufficiently dense time series", () => {
    expect(chooseRenderableChartType("line", 8)).toBe("line");
  });

  it("avoids underpowered scatter and crowded pie charts", () => {
    expect(chooseRenderableChartType("scatter", 6)).toBe("horizontalBar");
    expect(chooseRenderableChartType("pie", 7)).toBe("horizontalBar");
  });
});

describe("formatCompactNumber", () => {
  it("uses Chinese compact units", () => {
    expect(formatCompactNumber(403_000, "¥")).toBe("¥40.3万");
    expect(formatCompactNumber(125_000_000, "元")).toBe("1.3亿元");
  });

  it("keeps small values readable", () => {
    expect(formatCompactNumber(45.6, "%")).toBe("45.6%");
  });
});

describe("buildHeatmapRawData", () => {
  const heatmapRows = [
    { x: "A", y: "Q1", count: 42 },
    { x: "A", y: "Q2", count: 58 },
  ];

  it("derives heatmap value from yFields[1] when rows have no literal 'value'", () => {
    const chart = {
      type: "heatmap",
      dataset: "ds1",
      encodings: {
        x: { field: "x" },
        y: { fields: ["y", "count"] },
      },
    };
    const rawData = buildHeatmapRawData(chart, heatmapRows);
    expect(rawData).not.toBeUndefined();
    expect(rawData!.x).toBe("x");
    expect(rawData!.y).toBe("y");
    const rows = rawData!.rows as Array<Record<string, unknown>>;
    expect(rows[0].value).toBe(42);
    expect(rows[1].value).toBe(58);
  });

  it("falls back to encodings.matrix.field when no yFields[1]", () => {
    const chart = {
      type: "heatmap",
      dataset: "ds1",
      encodings: {
        x: { field: "x" },
        y: { field: "y" },
        matrix: { field: "count" },
      },
    };
    const rawData = buildHeatmapRawData(chart, heatmapRows);
    expect(rawData).not.toBeUndefined();
    expect((rawData!.rows as Array<Record<string, unknown>>)[0].value).toBe(42);
  });

  it("returns undefined for non-heatmap chart types", () => {
    const chart = { type: "bar", dataset: "ds1", encodings: {} };
    expect(buildHeatmapRawData(chart, [])).toBeUndefined();
  });
});

describe("validateChartMetadata", () => {
  it("passes for valid chart", () => {
    const result = validateChartMetadata({ type: "bar", dataset: "ds1" });
    expect(result.valid).toBe(true);
  });

  it("fails for missing type", () => {
    const result = validateChartMetadata({ dataset: "ds1" });
    expect(result.valid).toBe(false);
  });

  it("fails for missing dataset", () => {
    const result = validateChartMetadata({ type: "bar" });
    expect(result.valid).toBe(false);
  });
});
