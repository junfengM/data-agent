Name: Validate Data
Use When: The user needs to QA an analysis, validate methodology, check calculations, or review data quality before sharing.

# Data Validation Template

## Output Contract

Generate a Markdown report with this exact structure:

```markdown
# [Analysis Name]: Validation Report

**Analysis Being Validated:** [name/description]
**Audience:** [who requested the validation]
**Analysis Project:** [project name]
**Date:** [date]

## Validation Summary

**Overall Status:** [PASS / PASS WITH CAVEATS / FAIL]

[One paragraph: key findings, critical issues, and recommendation on whether to proceed]

## Methodology Review

### Data Sources
| Source | Status | Issues | Recommendation |
|--------|--------|--------|----------------|
| [source] | [OK/Issue/Blocked] | [issues if any] | [action] |

### Calculation Logic
| Calculation | Expected | Actual | Status |
|-------------|----------|--------|--------|
| [calc name] | [expected] | [actual] | [OK/Issue] |

### Assumptions
| Assumption | Validity | Impact if Wrong | Validation |
|------------|----------|-----------------|------------|
| [assumption] | [Valid/Risky/Invalid] | [High/Med/Low] | [how validated] |

## Data Quality Assessment

### Completeness
- [Field 1]: [% complete], [issues]
- [Field 2]: [% complete], [issues]

### Accuracy
- [Check 1]: [result], [issues]
- [Check 2]: [result], [issues]

### Consistency
- [Cross-check 1]: [result], [issues]
- [Cross-check 2]: [result], [issues]

## Analytical Pitfalls

| Pitfall | Risk Level | Status | Mitigation |
|---------|------------|--------|------------|
| [pitfall] | [High/Med/Low] | [Addressed/Not Addressed] | [mitigation] |

Common pitfalls checked:
- [ ] Survivorship bias
- [ ] Selection bias
- [ ] Simpson's paradox
- [ ] Correlation vs causation
- [ ] Cherry-picking time periods
- [ ] Ignoring confounders
- [ ] Base rate neglect
- [ ] Regression to the mean

## Evidence Strength

| Claim | Evidence Level | Supporting Data | Caveats |
|-------|---------------|-----------------|---------|
| [claim] | [Strong/Moderate/Weak] | [data] | [caveats] |

## Issues Found

### Critical (Must Fix)
1. [Issue 1]: [description, impact, recommendation]
2. [Issue 2]: [description, impact, recommendation]

### Important (Should Fix)
1. [Issue 1]: [description, impact, recommendation]
2. [Issue 2]: [description, impact, recommendation]

### Minor (Nice to Fix)
1. [Issue 1]: [description, impact, recommendation]
2. [Issue 2]: [description, impact, recommendation]

## Recommendations

### Before Sharing
- [ ] [Action 1]
- [ ] [Action 2]
- [ ] [Action 3]

### For Future Analysis
- [ ] [Improvement 1]
- [ ] [Improvement 2]

## Conclusion

[Clear statement on whether the analysis is ready to share, what caveats to include, and what follow-up is needed]

---

*Validation methodology: [what checks were performed]*
*Reviewer: [who performed the validation]*
```

## Rules

1. Overall status must be one of: PASS, PASS WITH CAVEATS, FAIL
2. Every issue must be categorized as Critical, Important, or Minor
3. Analytical pitfalls checklist must be explicitly evaluated
4. Evidence strength must be rated for each key claim
5. Recommendations must be specific and actionable
6. Conclusion must clearly state whether to proceed with sharing
