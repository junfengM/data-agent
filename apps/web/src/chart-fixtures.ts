// Chart data fixtures for manual smoke testing
// Each fixture represents the data shape the manifest-to-ChartData adapter produces

type ChartRow = {
  label: string;
  value: number;
  secondary_value?: number;
  min?: number;
  q1?: number;
  q3?: number;
  max?: number;
  [key: string]: unknown;
};

type ChartFixture = {
  chart_type: string;
  rows: ChartRow[];
  source?: string;
  unit?: string;
  description?: string;
};

// heatmap additionally carries rawData with matrix fields
type HeatmapRawData = {
  rows: Array<Record<string, unknown>>;
  x: string;
  y: string;
};

export const chartFixtures: Record<string, ChartFixture> = {
  boxPlot: {
    chart_type: "boxPlot",
    rows: [
      { label: "A", value: 100, min: 50, q1: 75, q3: 125, max: 150 },
      { label: "B", value: 200, min: 120, q1: 160, q3: 240, max: 280 },
      { label: "C", value: 150, min: 80, q1: 110, q3: 180, max: 220 },
      { label: "D", value: 180, min: 100, q1: 140, q3: 210, max: 260 },
    ],
    description: "Box-and-whisker plot with min/q1/median/q3/max per category",
  },

  heatmap: {
    chart_type: "heatmap",
    rows: [
      { label: "Jan-手机", value: 45 },
      { label: "Jan-电脑", value: 30 },
      { label: "Jan-平板", value: 22 },
      { label: "Feb-手机", value: 52 },
      { label: "Feb-电脑", value: 35 },
      { label: "Feb-平板", value: 28 },
      { label: "Mar-手机", value: 60 },
      { label: "Mar-电脑", value: 40 },
      { label: "Mar-平板", value: 33 },
    ],
    description: "Heatmap rows — rawData.x='month', rawData.y='product', value=intensity",
  },

  stackedBar: {
    chart_type: "stackedBar",
    rows: [
      { label: "Jan", value: 100, secondary_value: 50 },
      { label: "Feb", value: 120, secondary_value: 60 },
      { label: "Mar", value: 140, secondary_value: 70 },
      { label: "Apr", value: 130, secondary_value: 65 },
    ],
    description: "Stacked bar with primary value and secondary_value for dual series",
  },

  dualLine: {
    chart_type: "line",
    rows: [
      { label: "Q1", value: 220, secondary_value: 180 },
      { label: "Q2", value: 250, secondary_value: 200 },
      { label: "Q3", value: 290, secondary_value: 230 },
      { label: "Q4", value: 310, secondary_value: 260 },
    ],
    description: "Dual-line chart: value=primary series, secondary_value=comparison series",
  },

  waterfall: {
    chart_type: "waterfall",
    rows: [
      { label: "起点", value: 500 },
      { label: "收入", value: 200 },
      { label: "支出", value: -80 },
      { label: "调整", value: 30 },
      { label: "终点", value: 650 },
    ],
    description: "Waterfall chart showing cumulative flow between values",
  },
};

// rawData companion for the heatmap fixture
export const heatmapRawData: HeatmapRawData = {
  rows: [
    { month: "Jan", product: "手机", value: 45 },
    { month: "Jan", product: "电脑", value: 30 },
    { month: "Jan", product: "平板", value: 22 },
    { month: "Feb", product: "手机", value: 52 },
    { month: "Feb", product: "电脑", value: 35 },
    { month: "Feb", product: "平板", value: 28 },
    { month: "Mar", product: "手机", value: 60 },
    { month: "Mar", product: "电脑", value: 40 },
    { month: "Mar", product: "平板", value: 33 },
  ],
  x: "month",
  y: "product",
};
