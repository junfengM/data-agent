Name: Product & Business Analysis
Use When: The user needs data-backed evidence to make a product or business decision — choosing a direction, prioritizing an opportunity, evaluating a change, sizing a market.

# Product & Business Analysis Template

## Output Contract

Generate a Markdown report with this exact structure:

```markdown
# [Analysis Title]: Decision-Oriented Analysis

**Decision:** [what decision this analysis informs]
**Audience:** [who will use this and what they can act on]
**Analysis Project:** [project name]
**Date:** [date]

## Recommendation (Answer First)

[One paragraph: what they should believe or do, why the evidence supports it, and the estimated impact]

## Key Evidence

- **[Finding 1]:** [specific number + interpretation]
- **[Finding 2]:** [specific number + interpretation]
- **[Finding 3]:** [specific number + interpretation]

## Opportunity Sizing

[If applicable: quantify the size of the opportunity or problem]

| Opportunity | Size | Confidence | Addressability |
|-------------|------|------------|----------------|
| [name] | [value/range] | High/Med/Low | [how actionable] |

## Detailed Analysis

### [Analysis Dimension 1]

[Evidence from analysis steps, with tables and charts]

### [Analysis Dimension 2]

[Evidence from analysis steps]

## Risks & Tradeoffs

- [Risk 1: what could go wrong if action is taken]
- [Risk 2: what opportunity cost is involved]
- [Risk 3: what assumptions could change the conclusion]

## Decision Alternatives

[Briefly note alternatives that were considered and why they are not recommended]

## Next Steps

- [Immediate next action]
- [Follow-up analysis that would improve confidence]

---

*Caveats: [data limitations, unknowns, confidence levels]*
*Reproducibility: analysis steps and code are in the run log*
```

## Rules

1. The recommendation must be specific enough to act on — not "improve retention" but "launch re-engagement email for users inactive 7+ days, estimated to recover XX users/week"
2. Every finding in "Key Evidence" must cite a specific number from the analysis
3. Opportunity sizing must include a confidence level and addressability assessment
4. If the data doesn't support a strong recommendation, say so explicitly rather than forcing a weak one
5. Decision alternatives show the reader you considered other paths — this builds trust
