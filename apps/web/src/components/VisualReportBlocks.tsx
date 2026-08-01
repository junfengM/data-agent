import React from "react";
import { AlertTriangle, ArrowUpRight, Lightbulb, Target } from "lucide-react";

type Row = Record<string, unknown>;
type DatasetMap = Record<string, Row[]>;

type Props = {
  block: Row;
  datasets: DatasetMap;
};

export function VisualAutoOverview({ cards, tables, datasets }: { cards: Row[]; tables: Row[]; datasets: DatasetMap }) {
  const kpis = deriveKpisFromCards(cards, datasets).slice(0, 8);
  const { positive, negative } = deriveRankingsFromTables(tables, datasets);
  if (!kpis.length && !positive.length && !negative.length) return null;

  return (
    <section className="visual-auto-overview">
      <header className="visual-auto-header">
        <span>报告概览</span>
        <h3>核心指标与主要贡献</h3>
      </header>
      {kpis.length ? (
        <VisualKpiGrid block={{ title: "核心指标速览", items: kpis }} datasets={datasets} />
      ) : null}
      {positive.length || negative.length ? (
        <VisualLeaderboardPair
          block={{
            title: "贡献项排行",
            positive,
            negative,
          }}
          datasets={datasets}
        />
      ) : null}
    </section>
  );
}

export function VisualExecutiveStoryboard({ block, datasets }: Props) {
  const items = blockItems(block, datasets).slice(0, 6);
  if (!items.length) return null;
  return (
    <section className="visual-block visual-executive-storyboard">
      <BlockHeader block={block} fallback="核心结论速览" />
      <div className="visual-executive-grid">
        {items.map((item, index) => {
          const kind = storyKind(item);
          const metrics = Array.isArray(item.metrics) ? item.metrics.slice(0, 3) : [];
          return (
            <article className={`visual-executive-card ${kind}`} key={index}>
              <div className="visual-executive-card-top">
                <span className="visual-executive-icon">{storyIcon(kind)}</span>
                <span className="visual-executive-kind">{storyKindLabel(kind)}</span>
              </div>
              <h4>{text(item.headline ?? item.title ?? item.label, `结论 ${index + 1}`)}</h4>
              {metrics.length ? <div className="visual-executive-metrics">{metrics.map((metric, metricIndex) => <strong key={metricIndex}>{text(metric, "")}</strong>)}</div> : null}
              <p>{text(item.body ?? item.summary ?? item.text, "")}</p>
            </article>
          );
        })}
      </div>
    </section>
  );
}

export function VisualAdaptiveStory({ block, datasets }: Props) {
  const items = blockItems(block, datasets).slice(0, 8);
  if (!items.length) return null;
  const variant = ["mosaic", "signals", "steps", "split"].includes(text(block.variant, ""))
    ? text(block.variant, "mosaic")
    : "mosaic";
  return (
    <section className={`visual-block visual-adaptive-story visual-adaptive-${variant}`}>
      <BlockHeader block={block} fallback="重点拆解" />
      <div className="visual-adaptive-grid">
        {items.map((item, index) => {
          const kind = storyKind(item);
          const metrics = Array.isArray(item.metrics) ? item.metrics.slice(0, 3) : [];
          return (
            <article className={kind} key={index}>
              {variant === "steps" ? <span className="visual-adaptive-index">{index + 1}</span> : <span className="visual-adaptive-signal">{storyIcon(kind)}</span>}
              <div>
                <h4>{text(item.headline ?? item.title ?? item.label, `重点 ${index + 1}`)}</h4>
                {metrics.length ? <div className="visual-adaptive-metrics">{metrics.map((metric, metricIndex) => <b key={metricIndex}>{text(metric, "")}</b>)}</div> : null}
                <p>{text(item.body ?? item.summary ?? item.text, "")}</p>
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}

export function VisualKpiGrid({ block, datasets }: Props) {
  const items = blockItems(block, datasets);
  if (!items.length) return null;
  return (
    <section className="visual-block visual-kpi-grid-block">
      <BlockHeader block={block} fallback="核心指标" />
      <div className="visual-kpi-grid">
        {items.map((item, index) => (
          <article className={`visual-kpi-card ${directionClass(item)}`} key={index}>
            <span className="visual-kpi-label">{text(item.label ?? item.name ?? item.metric, "指标")}</span>
            <strong className="visual-kpi-value">{text(item.value ?? item.current ?? item.current_value, "-")}</strong>
            <div className="visual-kpi-meta">
              {item.previous != null || item.compare != null ? <span>对比 {text(item.previous ?? item.compare, "-")}</span> : null}
              {item.delta != null || item.change != null ? <b>{text(item.delta ?? item.change, "")}</b> : null}
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

export function VisualTrendPanel({ block, datasets }: Props) {
  const items = blockItems(block, datasets).slice(0, 16);
  if (items.length < 2) return null;
  const values = items.map((item) => numeric(item.value ?? item.amount ?? item.current)).filter(Number.isFinite);
  const minValue = Math.min(...values, 0);
  const maxValue = Math.max(...values, 1);
  const spread = Math.max(maxValue - minValue, 1);
  return (
    <section className="visual-block visual-trend-panel">
      <BlockHeader block={block} fallback="趋势变化" />
      <div className="visual-trend-list">
        {items.map((item, index) => {
          const value = numeric(item.value ?? item.amount ?? item.current);
          const width = Number.isFinite(value) ? Math.max(3, ((value - minValue) / spread) * 100) : 3;
          return (
            <article className="visual-composition-row" key={index}>
              <div className="visual-composition-label">
                <strong>{text(item.label ?? item.name ?? item.period, `阶段 ${index + 1}`)}</strong>
                <span>{text(item.value ?? item.amount ?? item.current, "-")}</span>
              </div>
              <div className="visual-composition-track"><span style={{ width: `${width}%` }} /></div>
            </article>
          );
        })}
      </div>
      <BlockNote block={block} />
    </section>
  );
}

export function VisualMetricChange({ block, datasets }: Props) {
  const items = blockItems(block, datasets).slice(0, 6);
  if (!items.length) return null;
  return (
    <section className="visual-block visual-metric-change">
      <BlockHeader block={block} fallback="指标变化" />
      <div className="visual-change-grid">
        {items.map((item, index) => (
          <article className={`visual-change-card ${directionClass(item)}`} key={index}>
            <span className="visual-change-label">{text(item.label ?? item.name, `指标 ${index + 1}`)}</span>
            <div className="visual-change-values">
              <strong>{text(item.start ?? item.previous ?? item.from, "-")}</strong>
              <span aria-hidden="true">→</span>
              <strong>{text(item.end ?? item.current ?? item.to, "-")}</strong>
            </div>
            {item.delta != null ? <b className="visual-change-delta">{text(item.delta, "")}</b> : null}
            {item.context != null ? <p>{text(item.context, "")}</p> : null}
          </article>
        ))}
      </div>
    </section>
  );
}

export function VisualForecastBand({ block, datasets }: Props) {
  const items = blockItems(block, datasets).slice(0, 10);
  if (!items.length) return null;
  return (
    <section className="visual-block visual-forecast-band">
      <BlockHeader block={block} fallback="预测区间" />
      <div className="visual-summary-grid">
        {items.map((item, index) => (
          <article key={index}>
            <strong>{text(item.label ?? item.name ?? item.period, `情景 ${index + 1}`)}</strong>
            <p>{text(item.lower, "-")} / <b>{text(item.value ?? item.forecast ?? item.expected, "-")}</b> / {text(item.upper, "-")}</p>
          </article>
        ))}
      </div>
      <BlockNote block={block} />
    </section>
  );
}

export function VisualStageTimeline({ block, datasets }: Props) {
  const items = blockItems(block, datasets).slice(0, 8);
  if (!items.length) return null;
  return (
    <section className="visual-block visual-stage-timeline">
      <BlockHeader block={block} fallback="阶段路线图" />
      <div className="visual-timeline-list">
        {items.map((item, index) => {
          const actions = Array.isArray(item.actions) ? item.actions : [];
          const details = Array.isArray(item.details) ? item.details : [];
          return (
            <article className="visual-timeline-item" key={index}>
              <span className="visual-timeline-index">{index + 1}</span>
              <div>
                <h4>{text(item.label ?? item.period ?? item.title, `阶段 ${index + 1}`)}</h4>
                {item.summary != null ? <p>{text(item.summary, "")}</p> : null}
                {details.length ? <div className="visual-timeline-tags">{details.map((detail, detailIndex) => <span key={detailIndex}>{text(detail, "")}</span>)}</div> : null}
                {actions.length ? <ul>{actions.map((action, actionIndex) => <li key={actionIndex}>{text(action, "")}</li>)}</ul> : null}
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}

export function VisualComparisonGrid({ block, datasets }: Props) {
  const items = blockItems(block, datasets).slice(0, 8);
  if (!items.length) return null;
  return (
    <section className="visual-block visual-comparison-grid">
      <BlockHeader block={block} fallback="重点对比" />
      <div className="visual-comparison-cards">
        {items.map((item, index) => {
          const metrics = Array.isArray(item.metrics) ? item.metrics.filter(isRecord) : [];
          return (
            <article key={index}>
              <h4>{text(item.label ?? item.name, `项目 ${index + 1}`)}</h4>
              <dl>
                {metrics.map((metric, metricIndex) => (
                  <div key={metricIndex}>
                    <dt>{text(metric.label ?? metric.name, "指标")}</dt>
                    <dd>{text(metric.value, "-")}</dd>
                  </div>
                ))}
              </dl>
              {item.note != null ? <p>{text(item.note, "")}</p> : null}
            </article>
          );
        })}
      </div>
    </section>
  );
}

export function VisualDeltaBridge({ block, datasets }: Props) {
  const items = blockItems(block, datasets);
  if (!items.length) return null;
  return (
    <section className="visual-block visual-delta-bridge-block">
      <BlockHeader block={block} fallback="变化拆解" />
      <div className="visual-delta-bridge">
        {items.map((item, index) => (
          <React.Fragment key={index}>
            <article className={`visual-bridge-node ${directionClass(item)}`}>
              <span>{text(item.label ?? item.name ?? item.driver, `因素 ${index + 1}`)}</span>
              <strong>{text(item.value ?? item.delta ?? item.change, "-")}</strong>
            </article>
            {index < items.length - 1 ? <span className="visual-bridge-plus">+</span> : null}
          </React.Fragment>
        ))}
      </div>
      <BlockNote block={block} />
    </section>
  );
}

export function VisualLeaderboardPair({ block, datasets }: Props) {
  const positive = namedItems(block, datasets, ["positive", "growth", "top", "winners", "left"]);
  const negative = namedItems(block, datasets, ["negative", "drag", "bottom", "losers", "right"]);
  const fallback = blockItems(block, datasets);
  const leftItems = positive.length ? positive : fallback.filter((item) => directionClass(item) !== "down").slice(0, 6);
  const rightItems = negative.length ? negative : fallback.filter((item) => directionClass(item) === "down").slice(0, 6);
  if (!leftItems.length && !rightItems.length) return null;
  return (
    <section className="visual-block visual-leaderboard-block">
      <BlockHeader block={block} fallback="贡献排行" />
      <div className="visual-leaderboard-pair">
        {leftItems.length ? <Leaderboard title={text(block.left_title ?? block.positive_title, "增长贡献 Top")} items={leftItems} tone="up" /> : null}
        {rightItems.length ? <Leaderboard title={text(block.right_title ?? block.negative_title, "拖累贡献 Top")} items={rightItems} tone="down" /> : null}
      </div>
    </section>
  );
}

export function VisualCompositionPanel({ block, datasets }: Props) {
  const items = blockItems(block, datasets).slice(0, 8);
  if (!items.length) return null;
  const maxValue = Math.max(...items.map((item) => Math.abs(numeric(item.value ?? item.share ?? item.percent ?? item.amount))), 1);
  return (
    <section className="visual-block visual-composition-block">
      <BlockHeader block={block} fallback="结构分布" />
      <div className="visual-composition-list">
        {items.map((item, index) => (
          <article className="visual-composition-row" key={index}>
            <div className="visual-composition-label">
              <strong>{text(item.label ?? item.name ?? item.dimension, `项目 ${index + 1}`)}</strong>
              <span>{text(item.value ?? item.share ?? item.percent ?? item.amount, "-")}</span>
            </div>
            <div className="visual-composition-track"><span style={{ width: `${Math.max(3, (Math.abs(numeric(item.value ?? item.share ?? item.percent ?? item.amount)) / maxValue) * 100)}%` }} /></div>
          </article>
        ))}
      </div>
    </section>
  );
}

export function VisualDecisionMatrix({ block, datasets }: Props) {
  const items = blockItems(block, datasets).slice(0, 8);
  if (!items.length) return null;
  return (
    <section className="visual-block visual-decision-matrix">
      <BlockHeader block={block} fallback="决策矩阵" />
      <div className="visual-summary-grid">
        {items.map((item, index) => (
          <article key={index}>
            <strong>{text(item.label ?? item.name ?? item.option, `方案 ${index + 1}`)}</strong>
            <p>收益/影响：{text(item.value ?? item.score ?? item.impact, "-")}</p>
            {item.risk != null ? <p>风险/投入：{text(item.risk, "-")}</p> : null}
          </article>
        ))}
      </div>
    </section>
  );
}

export function VisualDataQualityPanel({ block, datasets }: Props) {
  const items = blockItems(block, datasets).slice(0, 10);
  const body = text(block.text ?? block.body ?? block.summary, "");
  if (!items.length && !body) return null;
  return (
    <section className="visual-block visual-risk-panel visual-data-quality-panel">
      <BlockHeader block={block} fallback="数据质量提示" />
      {body ? <p className="visual-risk-intro">{body}</p> : null}
      {items.length ? (
        <ul className="visual-risk-list">
          {items.map((item, index) => <li key={index}>{text(item.label ?? item.name ?? item.field, `字段 ${index + 1}`)}：{text(item.value ?? item.missing, "-")}{item.total != null ? ` / ${text(item.total, "-")}` : ""}</li>)}
        </ul>
      ) : null}
    </section>
  );
}

export function VisualInsightBanner({ block }: { block: Row }) {
  const body = text(block.text ?? block.body ?? block.summary ?? block.insight, "");
  if (!body) return null;
  return (
    <section className="visual-block visual-insight-banner">
      <span className="visual-insight-icon">★</span>
      <div>
        <strong>{text(block.title, "关键洞察")}</strong>
        <p>{body}</p>
      </div>
    </section>
  );
}

export function VisualRiskPanel({ block, datasets }: Props) {
  const items = blockItems(block, datasets);
  const body = text(block.text ?? block.body ?? block.summary, "");
  return (
    <section className="visual-block visual-risk-panel">
      <BlockHeader block={block} fallback="风险与注意事项" />
      {body ? <p className="visual-risk-intro">{body}</p> : null}
      {items.length ? <ul className="visual-risk-list">{items.map((item, index) => <li key={index}>{text(item.text ?? item.label ?? item.name ?? item.risk ?? item.value, "-")}</li>)}</ul> : null}
    </section>
  );
}

export function VisualNextActionList({ block, datasets }: Props) {
  const items = blockItems(block, datasets);
  if (!items.length) return null;
  return (
    <section className="visual-block visual-action-panel">
      <BlockHeader block={block} fallback="下一步重点" />
      <ol className="visual-action-list">{items.map((item, index) => <li key={index}>{text(item.text ?? item.label ?? item.action ?? item.name, "-")}</li>)}</ol>
    </section>
  );
}

export function VisualPageSummary({ block, datasets }: Props) {
  const items = blockItems(block, datasets);
  const body = text(block.body ?? block.text ?? block.summary, "");
  return (
    <section className="visual-block visual-page-summary">
      <BlockHeader block={block} fallback="本页结论" />
      {body ? <p>{body}</p> : null}
      {items.length ? <div className="visual-summary-grid">{items.map((item, index) => <article key={index}>{text(item.text ?? item.label ?? item.name ?? item.summary, "-")}</article>)}</div> : null}
    </section>
  );
}

function Leaderboard({ title, items, tone }: { title: string; items: Row[]; tone: "up" | "down" }) {
  const maxValue = Math.max(...items.map((item) => Math.abs(numeric(item.value ?? item.delta ?? item.change ?? item.amount))), 1);
  return (
    <article className={`visual-leaderboard ${tone}`}>
      <h4>{title}</h4>
      <div className="visual-rank-list">
        {items.slice(0, 8).map((item, index) => (
          <div className="visual-rank-row" key={index}>
            <span className="visual-rank-badge">{index + 1}</span>
            <div className="visual-rank-main">
              <span><strong>{text(item.label ?? item.name ?? item.dimension ?? item.item, `项目 ${index + 1}`)}</strong><b>{text(item.value ?? item.delta ?? item.change ?? item.amount, "-")}</b></span>
              <div className="visual-rank-track"><span style={{ width: `${Math.max(3, (Math.abs(numeric(item.value ?? item.delta ?? item.change ?? item.amount)) / maxValue) * 100)}%` }} /></div>
            </div>
          </div>
        ))}
      </div>
    </article>
  );
}

function BlockHeader({ block, fallback }: { block: Row; fallback: string }) {
  const title = text(block.title ?? block.heading, fallback);
  const subtitle = text(block.subtitle ?? block.description ?? block.takeaway, "");
  return <header className="visual-block-header"><h3>{title}</h3>{subtitle ? <p>{subtitle}</p> : null}</header>;
}

function BlockNote({ block }: { block: Row }) {
  const note = text(block.note ?? block.takeaway ?? block.summary, "");
  return note ? <p className="visual-block-note">{note}</p> : null;
}

function blockItems(block: Row, datasets: DatasetMap): Row[] {
  if (Array.isArray(block.items)) return block.items.filter(isRecord);
  if (Array.isArray(block.rows)) return block.rows.filter(isRecord);
  const key = text(block.dataset ?? block.dataset_id ?? block.datasetId, "");
  return key ? datasets[key] || [] : [];
}

function namedItems(block: Row, datasets: DatasetMap, keys: string[]): Row[] {
  for (const key of keys) {
    const value = block[key];
    if (Array.isArray(value)) return value.filter(isRecord);
  }
  const datasetKey = text(block[`${keys[0]}_dataset`] ?? block[`${keys[0]}Dataset`], "");
  return datasetKey ? datasets[datasetKey] || [] : [];
}

function deriveKpisFromCards(cards: Row[], datasets: DatasetMap): Row[] {
  const items: Row[] = [];
  for (const card of cards) {
    const datasetKey = text(card.dataset, "");
    const row = datasetKey ? datasets[datasetKey]?.[0] : undefined;
    const metrics = Array.isArray(card.metrics) ? card.metrics.filter(isRecord) : [];
    for (const metric of metrics) {
      const field = text(metric.field, "");
      if (!field) continue;
      items.push({
        label: text(metric.label, field),
        value: row ? text(row[field], "-") : "-",
      });
    }
  }
  return items;
}

function deriveRankingsFromTables(tables: Row[], datasets: DatasetMap): { positive: Row[]; negative: Row[] } {
  for (const table of tables) {
    const datasetKey = text(table.dataset, "");
    const rows = datasetKey ? datasets[datasetKey] || [] : [];
    const columns = Array.isArray(table.columns) ? table.columns.filter(isRecord) : [];
    if (!rows.length || !columns.length) continue;
    const fields = columns.map((column) => text(column.field ?? column.key, "")).filter(Boolean);
    const labelField = fields.find((field) => rows.some((row) => typeof row[field] === "string")) || fields[0];
    const valueField = fields.find((field) => rows.some((row) => Number.isFinite(numeric(row[field]))));
    if (!labelField || !valueField || labelField === valueField) continue;
    const ranked = rows
      .map((row) => ({
        label: text(row[labelField], "-"),
        value: text(row[valueField], "-"),
        numericValue: numeric(row[valueField]),
      }))
      .filter((row) => Number.isFinite(row.numericValue))
      .sort((a, b) => Math.abs(b.numericValue) - Math.abs(a.numericValue));
    if (!ranked.length) continue;
    return {
      positive: ranked.filter((row) => row.numericValue >= 0).slice(0, 6),
      negative: ranked.filter((row) => row.numericValue < 0).slice(0, 6),
    };
  }
  return { positive: [], negative: [] };
}

function directionClass(item: Row): "up" | "down" | "flat" {
  const raw = text(item.direction ?? item.trend ?? item.status ?? item.delta ?? item.change ?? item.value, "").toLowerCase();
  if (raw.includes("-") || raw.includes("降") || raw.includes("跌") || raw.includes("少")) return "down";
  if (raw.includes("+") || raw.includes("增") || raw.includes("升") || raw.includes("多")) return "up";
  return "flat";
}

function storyKind(item: Row): "opportunity" | "risk" | "action" | "signal" {
  const kind = text(item.kind ?? item.status ?? item.type, "signal").toLowerCase();
  if (kind.includes("risk") || kind.includes("风险")) return "risk";
  if (kind.includes("action") || kind.includes("动作")) return "action";
  if (kind.includes("opportunity") || kind.includes("机会")) return "opportunity";
  return "signal";
}

function storyKindLabel(kind: ReturnType<typeof storyKind>): string {
  return { opportunity: "增长机会", risk: "风险信号", action: "经营动作", signal: "关键判断" }[kind];
}

function storyIcon(kind: ReturnType<typeof storyKind>) {
  if (kind === "risk") return <AlertTriangle size={17} />;
  if (kind === "action") return <Target size={17} />;
  if (kind === "opportunity") return <ArrowUpRight size={17} />;
  return <Lightbulb size={17} />;
}

function numeric(value: unknown): number {
  if (typeof value === "number") return value;
  const parsed = Number(String(value ?? "").replace(/[^0-9.-]/g, ""));
  return parsed;
}

function text(value: unknown, fallback: string): string {
  if (value === null || value === undefined) return fallback;
  const result = String(value).trim();
  return result || fallback;
}

function isRecord(value: unknown): value is Row {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
