Name: Dashboard Summary
Use When: The analysis output should be a monitoring dashboard with KPI cards, trend indicators, and compact visual evidence — the user asks for a dashboard, monitoring view, or status overview.

# Dashboard Summary Template

## Output Contract

Generate a Markdown summary suitable for conversion to a dashboard artifact:

```markdown
# [Dashboard Title]

**Last Updated:** [date/time]
**Data Window:** [time range]
**Refresh Cadence:** [how often data should be refreshed]

## KPI Cards

| KPI | Current | Previous Period | Δ | Trend | Status |
|-----|---------|-----------------|---|-------|--------|
| [kpi 1] | [value] | [value] | [+/-XX%] | ↗/→/↘ | 🟢/🟡/🔴 |
| [kpi 2] | [value] | [value] | [+/-XX%] | ↗/→/↘ | 🟢/🟡/🔴 |
| ... | | | | | |

## Trend Indicators

- **[Metric 1]:** [direction + magnitude] over [time period]. [One-line interpretation.]
- **[Metric 2]:** [direction + magnitude] over [time period]. [One-line interpretation.]

## Charts

[Reference to chart artifacts generated during analysis]

## Alerts & Anomalies

[If any metrics crossed thresholds or showed unusual patterns]

## Key Observations

- [Observation 1 — data-backed, one sentence]
- [Observation 2]
- [Observation 3]

## Actions

- [Action 1 — owner, timeline]
- [Action 2 — owner, timeline]

---

*Dashboard generated from analysis run [run_id]*
*Caveats: [data freshness, known gaps, metric definitions]*
```

## Rules

1. KPI Cards: max 8 KPIs. Every KPI needs current, previous, delta, trend direction, and status.
2. Trend: ↗ = improving >5%, → = stable within ±5%, ↘ = declining >5%
3. Status: 🟢 = healthy (meeting target or improving), 🟡 = watch (stable but below target), 🔴 = alert (declining or below threshold)
4. Alerts section should flag metrics outside expected ranges with specific thresholds
5. Actions must have owners and timelines — this is an operational dashboard, not just a report
6. If no chart artifacts were generated, note this and suggest what charts would add value
