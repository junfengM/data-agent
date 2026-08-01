Name: KPI Report
Use When: The user asks for KPI results, scorecard, weekly/monthly metrics, or periodic performance summary against targets.

# KPI Report Template

## Output Contract

Generate a Markdown report with this exact structure:

```markdown
# [Period] KPI Report: [Business Area]

**Report Date:** [date]
**Analysis Project:** [project name]
**Data Sources:** [datasets used]

## Executive Summary

[2-3 sentences: overall performance, 1-2 key numbers, direction (up/down/flat), whether targets were met]

## KPI Scorecard

| KPI | Actual | Target | Δ | Status |
|-----|--------|--------|---|--------|
| [metric 1] | [value] | [target] | [+/-XX%] | 🟢/🟡/🔴 |
| ... | | | | |

## Key Drivers

### What Drove Performance

[2-3 bullet points explaining the biggest positive contributors, with numbers]

### What Dragged Performance

[2-3 bullet points explaining the biggest negative contributors, with numbers]

## Notable Changes

[Any unusual patterns, anomalies, or one-time events that affected results]

## Risks & Watch Items

- [Risk 1: what could go wrong, likelihood, impact]
- [Risk 2]

## Next Actions

- [Actionable next step 1]
- [Actionable next step 2]

---

*Caveats: [data limitations, sampling notes, definition notes]*
*Reproducibility: analysis steps and code are in the run log*
```

## Rules

1. Status indicators: 🟢 = met or exceeded target (≥100%), 🟡 = within 10% of target (90-100%), 🔴 = below target (<90%)
2. Every KPI must have an actual, target, delta, and status — if target is unknown, mark as N/A
3. Driver sections must cite specific numbers (not "increased" — say "increased 12% from 450 to 504")
4. Risks must be specific to the data observed, not generic
