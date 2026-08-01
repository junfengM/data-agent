import React from "react";
import {
  BarChart, Bar,
  AreaChart, Area,
  LineChart, Line,
  ScatterChart, Scatter,
  PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from "recharts";
import type { ChartData, JsonRecord } from "../types";
import { chooseRenderableChartType, formatCompactNumber } from "../utils/chartAdapters";

export const COLORS = ["#2563eb", "#d97706", "#0f766e", "#be123c", "#64748b"];

const SWITCHABLE_CHART_TYPES = new Set(["bar", "horizontalBar", "column", "line", "area", "pie", "leaderboard"]);
const CHART_TYPE_LABELS: Record<string, string> = {
  area: "面积",
  bar: "横向条形",
  column: "柱状",
  horizontalBar: "横向条形",
  leaderboard: "排行",
  line: "折线",
  pie: "环形",
};

export function RechartsRenderer({ chartData, colors, rawData, compatibleTypes = [] }: { chartData: ChartData; colors: string[]; rawData?: JsonRecord; compatibleTypes?: string[] }) {
  const viewOptions = Array.from(new Set([chartData.chart_type, ...compatibleTypes]))
    .filter((type) => SWITCHABLE_CHART_TYPES.has(type))
    .filter((type) => chooseRenderableChartType(type, chartData.rows.length) === type);
  const [selectedType, setSelectedType] = React.useState(chartData.chart_type);
  React.useEffect(() => setSelectedType(chartData.chart_type), [chartData.chart_type]);
  const requestedType = viewOptions.includes(selectedType) ? selectedType : chartData.chart_type;
  const effectiveChartType = chooseRenderableChartType(requestedType, chartData.rows.length);
  const fallbackMessage =
    effectiveChartType !== requestedType
      ? requestedType === "scatter"
        ? `仅 ${chartData.rows.length} 个观测点，改用条形比较以避免弱散点关系。`
        : requestedType === "pie"
          ? `分类超过 5 项，改用条形比较以便准确读取差异。`
          : `仅 ${chartData.rows.length} 个时间点，改用离散柱状比较。`
      : "";

  return (
    <div className="recharts-frame">
      {viewOptions.length > 1 ? (
        <div className="chart-view-switcher" aria-label="图表视图">
          {viewOptions.map((type) => (
            <button className={requestedType === type ? "active" : ""} key={type} onClick={() => setSelectedType(type)} type="button">
              {CHART_TYPE_LABELS[type] || type}
            </button>
          ))}
        </div>
      ) : null}
      {fallbackMessage ? <p className="chart-render-note">{fallbackMessage}</p> : null}
      <RechartsChartBody
        chartData={{ ...chartData, chart_type: effectiveChartType }}
        colors={colors}
        rawData={rawData}
      />
    </div>
  );
}

function RechartsChartBody({ chartData, colors, rawData }: { chartData: ChartData; colors: string[]; rawData?: JsonRecord }) {
  const { chart_type, rows, unit } = chartData;
  const chartHeight = Math.max(200, Math.min(rows.length * 32, 400));
  const formatValue = (value: unknown) => formatCompactNumber(Number(value ?? 0), unit);

  const rechartData = rows.map((row) => ({
    name: row.label,
    value: row.value,
    secondary: row.secondary_value,
    xValue: row.x_value,
  }));

  switch (chart_type) {
    case "line":
      return (
        <ResponsiveContainer width="100%" height={chartHeight}>
          <LineChart data={rechartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
            <XAxis dataKey="name" tick={{ fontSize: 12 }} />
            <YAxis tick={{ fontSize: 12 }} tickFormatter={(value) => formatValue(value)} width={72} />
            <Tooltip formatter={(value) => formatValue(value)} />
            <Line type="monotone" dataKey="value" stroke={colors[0]} strokeWidth={2} dot={{ r: 3 }} name={unit ?? "值"} />
            {rechartData[0]?.secondary !== undefined && (
              <Line type="monotone" dataKey="secondary" stroke={colors[1]} strokeWidth={2} dot={{ r: 3 }} strokeDasharray="5 5" name="对比" />
            )}
          </LineChart>
        </ResponsiveContainer>
      );

    case "area":
      return (
        <ResponsiveContainer width="100%" height={chartHeight}>
          <AreaChart data={rechartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
            <XAxis dataKey="name" tick={{ fontSize: 12 }} />
            <YAxis tick={{ fontSize: 12 }} tickFormatter={(value) => formatValue(value)} width={72} />
            <Tooltip formatter={(value) => formatValue(value)} />
            <Area type="monotone" dataKey="value" stroke={colors[0]} fill={colors[0]} fillOpacity={0.12} name={unit ?? "值"} />
          </AreaChart>
        </ResponsiveContainer>
      );

    case "scatter": {
      const scatterData = rechartData.map((d) => ({ x: d.xValue ?? 0, y: d.value, name: d.name }));
      return (
        <ResponsiveContainer width="100%" height={chartHeight}>
          <ScatterChart>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
            <XAxis dataKey="x" type="number" tick={{ fontSize: 12 }} tickFormatter={(value) => formatCompactNumber(Number(value))} />
            <YAxis dataKey="y" type="number" tick={{ fontSize: 12 }} tickFormatter={(value) => formatValue(value)} width={72} />
            <Tooltip formatter={(value) => formatValue(value)} />
            <Scatter data={scatterData} fill={colors[0]} />
          </ScatterChart>
        </ResponsiveContainer>
      );
    }

    case "pie":
      return (
        <ResponsiveContainer width="100%" height={chartHeight}>
          <PieChart>
            <Pie
              data={rechartData}
              dataKey="value"
              nameKey="name"
              cx="50%"
              cy="50%"
              outerRadius={80}
              label={({ name: pieName, percent }: { name?: string; percent?: number }) =>
                `${pieName ?? ""} ${((percent ?? 0) * 100).toFixed(0)}%`
              }
            >
              {rechartData.map((_, i) => (
                <Cell key={i} fill={colors[i % colors.length]} />
              ))}
            </Pie>
            <Tooltip formatter={(value) => formatValue(value)} />
            <Legend />
          </PieChart>
        </ResponsiveContainer>
      );

    case "leaderboard": {
      const sorted = [...rows].sort((a, b) => b.value - a.value).slice(0, 8);
      const leaderMax = Math.max(...sorted.map((r) => r.value), 1);
      const rankMedal = (r: number) => {
        const medals: Record<number, { bg: string; fg: string }> = {
          1: { bg: "#f59e0b", fg: "#fff" },
          2: { bg: "#94a3b8", fg: "#fff" },
          3: { bg: "#d97706", fg: "#fff" },
        };
        const m = medals[r];
        return (
          <span
            style={{
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              width: 26,
              height: 26,
              borderRadius: "50%",
              background: m ? m.bg : "#f1f5f9",
              color: m ? m.fg : "#64748b",
              fontSize: 12,
              fontWeight: 700,
              flexShrink: 0,
            }}
          >
            {r}
          </span>
        );
      };
      return (
        <div className="bar-chart" style={{ gap: 6 }}>
          {sorted.map((row, i) => (
            <div
              key={row.label}
              style={{
                display: "grid",
                gridTemplateColumns: "28px minmax(80px,140px) 1fr 64px",
                gap: 10,
                alignItems: "center",
              }}
            >
              {rankMedal(i + 1)}
              <span style={{ fontSize: 13, color: "#334155", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {row.label}
              </span>
              <div className="bar-track">
                <div className="bar-fill" style={{ width: `${(row.value / leaderMax) * 100}%`, background: colors[i % colors.length] }} />
              </div>
              <span style={{ fontSize: 12, color: "#64748b", textAlign: "right", fontWeight: 600 }}>
                {formatValue(row.value)}
              </span>
            </div>
          ))}
        </div>
      );
    }

    case "funnel": {
      const funnelMax = Math.max(...rows.map((r) => r.value), 1);
      return (
        <div className="bar-chart" style={{ gap: 4 }}>
          {rows.map((row, i) => {
            const pct = (row.value / funnelMax) * 100;
            return (
              <div key={row.label} style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, color: "#475569" }}>
                  <span style={{ fontWeight: 600 }}>{row.label}</span>
                  <span>{formatValue(row.value)}</span>
                </div>
                <div className="bar-track" style={{ height: 22, borderRadius: 4 }}>
                  <div
                    className="bar-fill"
                    style={{
                      width: `${pct}%`,
                      height: "100%",
                      borderRadius: 4,
                      background: `linear-gradient(90deg, ${colors[i % colors.length]}, ${colors[i % colors.length]}88)`,
                      marginLeft: `${(100 - pct) / 2}%`,
                    }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      );
    }

    case "waterfall": {
      let cumulative = 0;
      const waterfallData = rows.map((row) => {
        const base = cumulative;
        cumulative += row.value;
        return { name: row.label, base, value: row.value, total: cumulative };
      });
      const wfHeight = Math.max(260, Math.min(rows.length * 48, 420));
      return (
        <ResponsiveContainer width="100%" height={wfHeight}>
          <BarChart data={waterfallData} barCategoryGap="20%">
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" vertical={false} />
            <XAxis dataKey="name" tick={{ fontSize: 12 }} />
            <YAxis tick={{ fontSize: 12 }} tickFormatter={(value) => formatValue(value)} width={72} />
            <Tooltip
              formatter={(val, _name, props: { payload?: { name?: string; total?: number } }) => {
                const v = typeof val === "number" ? val : 0;
                const t = props?.payload?.total;
                return [v, t !== undefined ? `累计: ${t.toLocaleString()}` : String(v)];
              }}
            />
            <Bar dataKey="base" stackId="wf" fill="transparent" />
            <Bar dataKey="value" stackId="wf" fill={colors[0]} radius={[4, 4, 0, 0]} name={unit ?? "值"} />
          </BarChart>
        </ResponsiveContainer>
      );
    }

    case "boxPlot": {
      const svgW = rows.length * 80 + 80;
      const svgH = 280;
      const pad = { top: 20, right: 40, bottom: 40, left: 50 };
      const plotW = svgW - pad.left - pad.right;
      const plotH = svgH - pad.top - pad.bottom;
      const allVals = rows.flatMap((r) =>
        [r.min ?? r.value, r.q1 ?? r.value, r.value, r.q3 ?? r.value, r.max ?? r.value].filter(
          (v): v is number => v !== undefined
        )
      );
      const yMin = Math.min(...allVals, 0);
      const yMax = Math.max(...allVals, 1);
      const yScale = (v: number) => pad.top + plotH - ((v - yMin) / (yMax - yMin || 1)) * plotH;
      const xBand = plotW / (rows.length || 1);
      const boxW = Math.min(xBand * 0.5, 40);

      return (
        <svg width="100%" height={svgH} viewBox={`0 0 ${svgW} ${svgH}`} style={{ fontFamily: "system-ui, sans-serif" }}>
          {[0, 0.25, 0.5, 0.75, 1].map((frac) => {
            const v = yMin + frac * (yMax - yMin);
            const y = yScale(v);
            return (
              <g key={frac}>
                <line x1={pad.left - 5} x2={pad.left} y1={y} y2={y} stroke="#cbd5e1" />
                <text x={pad.left - 8} y={y + 4} textAnchor="end" fontSize={10} fill="#64748b">
                  {Number.isInteger(v) ? v : v.toFixed(1)}
                </text>
              </g>
            );
          })}
          {rows.map((row, i) => {
            const cx = pad.left + xBand * i + xBand / 2;
            const q1 = row.q1 ?? row.value * 0.75;
            const q3 = row.q3 ?? row.value * 1.25;
            const med = row.value;
            const rMin = row.min ?? med * 0.5;
            const rMax = row.max ?? med * 1.5;
            const yQ1 = yScale(q1);
            const yQ3 = yScale(q3);
            const yMed = yScale(med);
            const yMinV = yScale(rMin);
            const yMaxV = yScale(rMax);
            return (
              <g key={row.label}>
                <line x1={cx} x2={cx} y1={yMinV} y2={yMaxV} stroke="#64748b" strokeWidth={1.5} />
                <line x1={cx - boxW / 3} x2={cx + boxW / 3} y1={yMinV} y2={yMinV} stroke="#64748b" strokeWidth={1.5} />
                <line x1={cx - boxW / 3} x2={cx + boxW / 3} y1={yMaxV} y2={yMaxV} stroke="#64748b" strokeWidth={1.5} />
                <rect x={cx - boxW / 2} y={Math.min(yQ1, yQ3)} width={boxW} height={Math.abs(yQ3 - yQ1)} fill={colors[i % colors.length]} fillOpacity={0.25} stroke={colors[i % colors.length]} strokeWidth={1.5} rx={2} />
                <line x1={cx - boxW / 2} x2={cx + boxW / 2} y1={yMed} y2={yMed} stroke={colors[i % colors.length]} strokeWidth={2.5} />
                <text x={cx} y={svgH - pad.bottom + 16} textAnchor="middle" fontSize={11} fill="#334155">{row.label}</text>
              </g>
            );
          })}
        </svg>
      );
    }

    case "heatmap": {
      const rawRows = Array.isArray(rawData?.rows) ? (rawData.rows as JsonRecord[]) : [];
      const xField = typeof rawData?.x === "string" ? rawData.x : "column";
      const yField = typeof rawData?.y === "string" ? rawData.y : "label";
      const xSet = new Set<string>();
      const ySet = new Set<string>();
      const cellMap = new Map<string, number>();
      for (const r of rawRows) {
        const xv = String(r[xField] ?? "");
        const yv = String(r[yField] ?? "");
        const v = typeof r.value === "number" ? r.value : 0;
        if (xv && yv) { xSet.add(xv); ySet.add(yv); cellMap.set(`${yv}||${xv}`, v); }
      }
      const xLabels = [...xSet];
      const yLabels = [...ySet];
      if (!xLabels.length || !yLabels.length) {
        const vals = rows.map((r) => r.value);
        const hmMin = Math.min(...vals);
        const hmMax = Math.max(...vals, hmMin + 1);
        const cellH = Math.min(36, Math.max(22, 280 / rows.length));
        return (
          <div>
            <div style={{ display: "grid", gap: 2 }}>
              {rows.map((row) => {
                const ratio = (row.value - hmMin) / (hmMax - hmMin || 1);
                const alpha = 0.15 + ratio * 0.85;
                return (
                  <div key={row.label} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ width: 100, fontSize: 11, color: "#475569", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flexShrink: 0 }}>{row.label}</span>
                    <div style={{ flex: 1, height: cellH, borderRadius: 3, background: `rgba(99,102,241,${alpha})`, display: "flex", alignItems: "center", justifyContent: "flex-end", paddingRight: 8 }}>
                      <span style={{ fontSize: 11, fontWeight: 700, color: alpha > 0.5 ? "#fff" : "#334155" }}>{row.value.toLocaleString()}</span>
                    </div>
                  </div>
                );
              })}
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 10, fontSize: 11, color: "#64748b" }}>
              <span>{hmMin.toLocaleString()}</span>
              <div style={{ flex: 1, height: 8, borderRadius: 4, background: "linear-gradient(90deg, rgba(99,102,241,0.15), rgba(99,102,241,1))" }} />
              <span>{hmMax.toLocaleString()}</span>
            </div>
          </div>
        );
      }
      const hmVals = [...cellMap.values()];
      const hmMin = Math.min(...hmVals);
      const hmMax = Math.max(...hmVals, hmMin + 1);
      const cellW = Math.min(64, Math.max(36, 560 / xLabels.length));
      const cellH = Math.min(36, Math.max(22, 280 / yLabels.length));
      return (
        <div>
          <div style={{ overflowX: "auto" }}>
            <div style={{ display: "grid", gridTemplateColumns: `100px repeat(${xLabels.length}, ${cellW}px)`, gap: 2, minWidth: 100 + xLabels.length * cellW }}>
              <div />
              {xLabels.map((x) => (
                <div key={x} style={{ fontSize: 10, color: "#64748b", textAlign: "center", padding: "2px 0", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{x}</div>
              ))}
              {yLabels.map((y) => (
                <React.Fragment key={y}>
                  <div style={{ fontSize: 11, color: "#475569", display: "flex", alignItems: "center", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{y}</div>
                  {xLabels.map((x) => {
                    const cv = cellMap.get(`${y}||${x}`) ?? 0;
                    const ratio = (cv - hmMin) / (hmMax - hmMin || 1);
                    const alpha = 0.15 + ratio * 0.85;
                    return (
                      <div key={x} style={{ height: cellH, borderRadius: 2, background: `rgba(99,102,241,${alpha})`, display: "flex", alignItems: "center", justifyContent: "center" }}>
                        <span style={{ fontSize: 10, fontWeight: 600, color: alpha > 0.5 ? "#fff" : "#334155" }}>{cv.toLocaleString()}</span>
                      </div>
                    );
                  })}
                </React.Fragment>
              ))}
            </div>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 10, fontSize: 11, color: "#64748b" }}>
            <span>{hmMin.toLocaleString()}</span>
            <div style={{ flex: 1, height: 8, borderRadius: 4, background: "linear-gradient(90deg, rgba(99,102,241,0.15), rgba(99,102,241,1))" }} />
            <span>{hmMax.toLocaleString()}</span>
          </div>
        </div>
      );
    }

    case "sparkline":
      return (
        <ResponsiveContainer width="100%" height={80}>
          <LineChart data={rechartData}>
            <Line type="monotone" dataKey="value" stroke={colors[0]} strokeWidth={2} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      );

    case "horizontalBar":
      return (
        <ResponsiveContainer width="100%" height={chartHeight}>
          <BarChart data={rechartData} layout="vertical">
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" horizontal={false} />
            <XAxis type="number" tick={{ fontSize: 12 }} tickFormatter={(value) => formatValue(value)} />
            <YAxis dataKey="name" type="category" width={124} tick={{ fontSize: 12 }} />
            <Tooltip formatter={(value) => formatValue(value)} />
            <Bar dataKey="value" fill={colors[0]} radius={[0, 3, 3, 0]} name={unit ?? "值"} />
            {rechartData[0]?.secondary !== undefined && (
              <Bar dataKey="secondary" fill={colors[1]} radius={[0, 3, 3, 0]} name="对比" />
            )}
          </BarChart>
        </ResponsiveContainer>
      );

    case "column":
      return (
        <ResponsiveContainer width="100%" height={Math.max(240, chartHeight)}>
          <BarChart data={rechartData} barCategoryGap="28%">
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" vertical={false} />
            <XAxis dataKey="name" tick={{ fontSize: 12 }} />
            <YAxis tick={{ fontSize: 12 }} tickFormatter={(value) => formatValue(value)} width={72} />
            <Tooltip formatter={(value) => formatValue(value)} />
            <Bar dataKey="value" fill={colors[0]} radius={[3, 3, 0, 0]} name={unit ?? "值"} />
            {rechartData[0]?.secondary !== undefined && (
              <Bar dataKey="secondary" fill={colors[1]} radius={[3, 3, 0, 0]} name="对比" />
            )}
          </BarChart>
        </ResponsiveContainer>
      );

    case "stackedBar":
      return (
        <ResponsiveContainer width="100%" height={chartHeight}>
          <BarChart data={rechartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" vertical={false} />
            <XAxis dataKey="name" tick={{ fontSize: 12 }} />
            <YAxis tick={{ fontSize: 12 }} tickFormatter={(value) => formatValue(value)} width={72} />
            <Tooltip formatter={(value) => formatValue(value)} />
            <Bar dataKey="value" stackId="stack" fill={colors[0]} radius={[3, 3, 0, 0]} name={unit ?? "值"} />
            {rechartData[0]?.secondary !== undefined && (
              <Bar dataKey="secondary" stackId="stack" fill={colors[1]} radius={[3, 3, 0, 0]} name="对比" />
            )}
          </BarChart>
        </ResponsiveContainer>
      );

    case "stackedBar100": {
      const pctData = rechartData.map((d) => {
        const total = d.value + (d.secondary ?? 0);
        return total ? { name: d.name, value: (d.value / total) * 100, secondary: ((d.secondary ?? 0) / total) * 100 } : { name: d.name, value: 0, secondary: 0 };
      });
      return (
        <ResponsiveContainer width="100%" height={chartHeight}>
          <BarChart data={pctData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" vertical={false} />
            <XAxis dataKey="name" tick={{ fontSize: 12 }} />
            <YAxis tick={{ fontSize: 12 }} domain={[0, 100]} tickFormatter={(v: number) => `${v}%`} />
            <Tooltip formatter={(val) => [`${typeof val === "number" ? val.toFixed(1) : "0"}%`]} />
            <Bar dataKey="value" stackId="stack" fill={colors[0]} radius={[3, 3, 0, 0]} name={unit ?? "值"} />
            {pctData[0]?.secondary !== undefined && (
              <Bar dataKey="secondary" stackId="stack" fill={colors[1]} radius={[4, 4, 0, 0]} name="对比" />
            )}
          </BarChart>
        </ResponsiveContainer>
      );
    }

    case "horizontalStackedBar":
      return (
        <ResponsiveContainer width="100%" height={chartHeight}>
          <BarChart data={rechartData} layout="vertical">
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" horizontal={false} />
            <XAxis type="number" tick={{ fontSize: 12 }} tickFormatter={(value) => formatValue(value)} />
            <YAxis dataKey="name" type="category" width={124} tick={{ fontSize: 12 }} />
            <Tooltip formatter={(value) => formatValue(value)} />
            <Bar dataKey="value" stackId="stack-h" fill={colors[0]} radius={[0, 3, 3, 0]} name={unit ?? "值"} />
            {rechartData[0]?.secondary !== undefined && (
              <Bar dataKey="secondary" stackId="stack-h" fill={colors[1]} radius={[0, 4, 4, 0]} name="对比" />
            )}
          </BarChart>
        </ResponsiveContainer>
      );

    case "horizontalStackedBar100": {
      const hpctData = rechartData.map((d) => {
        const total = d.value + (d.secondary ?? 0);
        return total ? { name: d.name, value: (d.value / total) * 100, secondary: ((d.secondary ?? 0) / total) * 100 } : { name: d.name, value: 0, secondary: 0 };
      });
      return (
        <ResponsiveContainer width="100%" height={chartHeight}>
          <BarChart data={hpctData} layout="vertical">
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" horizontal={false} />
            <XAxis type="number" tick={{ fontSize: 12 }} domain={[0, 100]} tickFormatter={(v: number) => `${v}%`} />
            <YAxis dataKey="name" type="category" width={124} tick={{ fontSize: 12 }} />
            <Tooltip formatter={(val) => [`${typeof val === "number" ? val.toFixed(1) : "0"}%`]} />
            <Bar dataKey="value" stackId="stack-h" fill={colors[0]} radius={[0, 3, 3, 0]} name={unit ?? "值"} />
            {hpctData[0]?.secondary !== undefined && (
              <Bar dataKey="secondary" stackId="stack-h" fill={colors[1]} radius={[0, 4, 4, 0]} name="对比" />
            )}
          </BarChart>
        </ResponsiveContainer>
      );
    }

    case "bar":
    default:
      return (
        <ResponsiveContainer width="100%" height={chartHeight}>
          <BarChart data={rechartData} layout="vertical">
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" horizontal={false} />
            <XAxis type="number" tick={{ fontSize: 12 }} tickFormatter={(value) => formatValue(value)} />
            <YAxis dataKey="name" type="category" width={124} tick={{ fontSize: 12 }} />
            <Tooltip formatter={(value) => formatValue(value)} />
            <Bar dataKey="value" fill={colors[0]} radius={[0, 3, 3, 0]} name={unit ?? "值"} />
            {rechartData[0]?.secondary !== undefined && (
              <Bar dataKey="secondary" fill={colors[1]} radius={[0, 3, 3, 0]} name="对比" />
            )}
          </BarChart>
        </ResponsiveContainer>
      );
  }
}
