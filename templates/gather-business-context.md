Name: Gather Business Context
Use When: The user needs to gather, organize, and validate business context from documents, dashboards, chats, or other sources.

# Business Context Gathering Template

## Output Contract

Generate a Markdown report with this exact structure:

```markdown
# [Topic]: Business Context Summary

**Topic:** [what context was gathered for]
**Audience:** [who will use this context]
**Analysis Project:** [project name]
**Date:** [date]

## Context Summary

[One paragraph: key context findings and their implications for the analysis]

## Business Background

### Company/Product Context
- **Product:** [what product/service]
- **Market:** [target market]
- **Stage:** [growth stage, maturity, etc.]
- **Key Metrics:** [what metrics matter]

### Strategic Context
- **Goals:** [current strategic goals]
- **Priorities:** [what's most important now]
- **Constraints:** [what limits are there]

## Metric Definitions

| Metric | Definition | Source | Grain | Notes |
|--------|------------|--------|-------|-------|
| [metric] | [how it's calculated] | [where defined] | [daily/weekly/etc.] | [caveats] |

## Data Sources

| Source | Type | Status | Quality | Notes |
|--------|------|--------|---------|-------|
| [source] | [type] | [available/missing] | [good/issue] | [caveats] |

## Known Issues & Caveats

### Data Issues
- [Issue 1]: [description, impact, workaround]
- [Issue 2]: [description, impact, workaround]

### Business Context
- [Context 1]: [what changed, when, impact on analysis]
- [Context 2]: [what changed, when, impact on analysis]

## Stakeholder Input

### Key Stakeholders
| Stakeholder | Role | Input | Concerns |
|-------------|------|-------|----------|
| [name] | [role] | [input] | [concerns] |

### Consensus Points
- [Point 1]: [what everyone agrees on]
- [Point 2]: [what everyone agrees on]

### Disagreements
- [Disagreement 1]: [what's debated, who believes what]
- [Disagreement 2]: [what's debated, who believes what]

## Gaps & Follow-up

### Missing Context
- [Gap 1]: [what's missing, why it matters, how to fill it]
- [Gap 2]: [what's missing, why it matters, how to fill it]

### Recommended Follow-up
- [Action 1]: [what to do next]
- [Action 2]: [what to do next]

## Source Inventory

| Source | Type | URL/Path | Last Updated | Reliability |
|--------|------|----------|--------------|-------------|
| [source] | [type] | [location] | [date] | [high/med/low] |

---

*Context gathering methodology: [what sources were searched]*
*Completeness: [% of required context gathered]*
```

## Rules

1. Every metric definition must include source, grain, and calculation method
2. Known issues and caveats must be explicitly stated with impact assessment
3. Stakeholder disagreements must be documented with both perspectives
4. Gaps must be prioritized by impact on analysis
5. Source inventory must include reliability assessment
6. Context summary must highlight implications for analysis
