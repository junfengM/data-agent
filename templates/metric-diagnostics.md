Name: Metric Diagnostics
Use When: The user asks why a metric changed (went up/down), what caused a drop/spike, or needs root cause analysis.

# Metric Diagnostics Template

## Output Contract

Generate a Markdown report with this exact structure:

```markdown
# Metric Diagnostics: [Metric Name]

**Question:** [original question]
**Period Analyzed:** [time range]
**Analysis Project:** [project name]

## Summary (Answer First)

[One paragraph: the primary cause of the change, quantified. Cite contribution percentages or absolute numbers.]

## Metric Overview

| Period | Value | Change | % Change |
|--------|-------|--------|----------|
| Previous | [value] | — | — |
| Current | [value] | [Δ] | [+/-XX%] |

## Decomposition

[Break down the metric change into contributing factors. Each factor must have a direction and magnitude.]

### Factor 1: [Name] — Contributed [+/-XX%]

[Evidence: what changed, by how much, which segments/subgroups drove it]

### Factor 2: [Name] — Contributed [+/-XX%]

[Evidence]

### Unexplained Remainder: [+/-XX%]

[What portion of the change could not be attributed]

## Segment Analysis

[If applicable: break down by relevant dimensions (channel, region, product, user cohort)]

| Segment | Previous | Current | Δ | % of Total Change |
|---------|----------|---------|---|-------------------|
| [seg 1] | | | | |
| ... | | | | |

## Hypotheses Ruled Out

- [Hypothesis 1]: tested, not supported because [brief reason]
- [Hypothesis 2]: tested, not supported because [brief reason]

## Recommendation

[What action to take based on the root cause analysis]

---

*Caveats: [data limitations, completeness, confounding factors]*
*Reproducibility: analysis steps and code are in the run log*
```

## Rules

1. Decomposition must sum to approximately 100% of the observed change — if large portion is unexplained, say so explicitly
2. Every contributing factor must have a number, not just a direction
3. Segment analysis is required only when meaningful — do not add it if the data doesn't support meaningful segments
4. Ruled-out hypotheses are as important as confirmed ones — they save the reader from wrong conclusions
5. The recommendation must follow directly from the root cause — do not recommend actions unrelated to the evidence
