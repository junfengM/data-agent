Name: Executive Summary
Use When: The audience needs a one-page overview for leadership — the user says "summarize", "executive summary", "for leadership", "brief overview", or the analysis is complex and needs a distilled version.

# Executive Summary Template

## Output Contract

Generate a concise Markdown summary with this exact structure:

```markdown
# Executive Summary: [Topic]

**Date:** [date]
**Prepared for:** [audience]
**Based on:** [datasets / analysis runs]

## Bottom Line

[2-3 sentences maximum. The single most important thing the reader should know. Include the key number.]

## Key Numbers

| Metric | Value | Change | Signal |
|--------|-------|--------|--------|
| [metric 1] | [value] | [+/-XX%] | 🟢/🟡/🔴 |
| [metric 2] | [value] | [+/-XX%] | 🟢/🟡/🔴 |
| [metric 3] | [value] | [+/-XX%] | 🟢/🟡/🔴 |

## What This Means

[2-4 bullet points: implications for the business, decisions affected]

## What To Do

[1-3 recommended actions, each one sentence]

## Risks To Watch

- [Risk 1 — one line]
- [Risk 2 — one line]

---

*Full analysis available in the detailed report artifact.*
*Caveats: [critical limitations that leadership should know]*
```

## Rules

1. Maximum one page equivalent — every sentence must earn its place
2. No methodology details, no SQL, no code references — this is for decision-makers
3. Key Numbers table: max 5 rows, only the metrics that matter for the decision
4. Signal: 🟢 = positive/healthy, 🟡 = watch/mixed, 🔴 = concerning/needs attention
5. What To Do must be concrete and actionable, not "monitor" or "investigate further" unless genuinely the only option
6. If the evidence is weak or confidence is low, state it in the first sentence of Bottom Line
