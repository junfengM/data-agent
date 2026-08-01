Name: Market Sizing
Use When: The user needs to estimate market opportunity, TAM/SAM/SOM, or opportunity sizing with assumptions and sensitivity analysis.

# Market Sizing Template

## Output Contract

Generate a Markdown report with this exact structure:

```markdown
# [Market/Oportunity Name]: Market Sizing Analysis

**Decision:** [what decision this sizing informs]
**Audience:** [who will use this and what they can act on]
**Analysis Project:** [project name]
**Date:** [date]

## Executive Summary

[One paragraph: total addressable market estimate, key assumptions, and confidence level]

## Market Definition

### Target Market
- **Geography:** [regions included]
- **Customer Segment:** [who is included]
- **Product/Service:** [what is being sized]
- **Time Frame:** [forecast period]

### Methodology
- **Approach:** [top-down, bottom-up, or hybrid]
- **Data Sources:** [what data was used]
- **Key Assumptions:** [list critical assumptions]

## Market Size Estimates

| Metric | Estimate | Range (Low-High) | Confidence | Basis |
|--------|----------|------------------|------------|-------|
| TAM (Total Addressable Market) | [value] | [range] | [H/M/L] | [basis] |
| SAM (Serviceable Addressable Market) | [value] | [range] | [H/M/L] | [basis] |
| SOM (Serviceable Obtainable Market) | [value] | [range] | [H/M/L] | [basis] |

## Detailed Sizing

### [Sizing Dimension 1: e.g., by Customer Segment]

| Segment | Count | Revenue/Unit | Total | Share |
|---------|-------|--------------|-------|-------|
| [segment] | [count] | [value] | [total] | [%] |

### [Sizing Dimension 2: e.g., by Geography]

| Region | Market Size | Growth Rate | Key Drivers |
|--------|-------------|-------------|-------------|
| [region] | [value] | [%] | [drivers] |

## Sensitivity Analysis

### Key Variables

| Variable | Base Case | Optimistic | Pessimistic | Impact |
|----------|-----------|------------|-------------|--------|
| [variable] | [value] | [value] | [value] | [high/med/low] |

### Scenario Analysis

| Scenario | Assumptions | Market Size | Probability |
|----------|-------------|-------------|-------------|
| Bull Case | [assumptions] | [value] | [%] |
| Base Case | [assumptions] | [value] | [%] |
| Bear Case | [assumptions] | [value] | [%] |

## Validation & Caveats

### Data Quality
- [Data source 1]: [reliability, freshness, coverage]
- [Data source 2]: [reliability, freshness, coverage]

### Key Risks
- [Risk 1]: [what could invalidate the estimate]
- [Risk 2]: [what assumptions are most uncertain]

### Missing Data
- [Gap 1]: [what data would improve confidence]
- [Gap 2]: [what validation is still needed]

## Recommendations

- [Action 1]: [what to do with this sizing]
- [Action 2]: [what validation to pursue next]

---

*Caveats: [data limitations, unknowns, confidence levels]*
*Reproducibility: sizing methodology and code are in the run log*
```

## Rules

1. Always state the methodology (top-down, bottom-up, or hybrid) and justify the choice
2. Every estimate must have a confidence level and range (low-high)
3. Sensitivity analysis must identify the top 3 variables that most affect the estimate
4. Scenario analysis must include bull, base, and bear cases with probabilities
5. Data quality and caveats must be explicitly stated — do not hide uncertainty
6. Recommendations must be actionable and tied to the sizing results
