Name: Market Sizing
Use When: The user asks about market opportunity, TAM/SAM/SOM, revenue potential, customer count sizing, or commercial upside.

# Market Sizing

Size a market opportunity using TAM/SAM/SOM framework. This skill guides the agent through scope definition, methodology selection, model building, sensitivity analysis, and cross-validation. All inputs come from user-provided data files or stated assumptions — no external market data APIs are used.

## Mandatory Pre-Answer Gate

Before answering, searching sources, retrieving evidence, creating artifacts, or drafting output:

1. Load `$user-context` and run project preflight
2. Apply semantic-layer lookup if the request names or implies a metric, table, or business question
3. Apply source discovery and verification before drawing conclusions
4. Apply source access guardrail before querying sources

Do not skip preflight even when project context appears available.

## Workflow

1. **Define market scope.** What is being sized? Specify geography (country, region, city), customer segment (demographic, firmographic, behavioral), time horizon (annual, 3-year, 5-year), and unit (revenue in currency, units sold, active users, transactions). Without a clear scope boundary, sizing becomes unbounded guesswork. If the user has not specified these dimensions, ask before proceeding.

2. **Choose methodology.** Select and state the approach. Prefer bottom-up when unit-level data is available (customer counts, transaction records, pricing data). Use top-down when reliable industry reports or census data exist. Fall back to analog when neither is available but a comparable market can serve as a reference point.
   - **Top-down**: start from industry reports, census data, or published market figures. Apply penetration rate, market share, or segmentation filters to narrow to the target scope.
   - **Bottom-up**: build from unit-level data. Customer count × ARPU, transaction volume × average price, or addressable population × adoption rate. More defensible when inputs come from observed data rather than assumptions.
   - **Analog**: benchmark against a comparable market, geography, or product with known size and adjust for differences in population, GDP, adoption curve, or pricing. State the analog explicitly and list each adjustment factor.

3. **Inventory available data.** List every data point the user has provided or the project contains. For each: the value, the source file, and whether it is observed (from data), estimated (from research), or assumed (judgment call). Identify gaps where assumptions are needed. Do not proceed to model building until the inventory is complete and the user has acknowledged any critical gaps. Note: published reports and industry figures the user provides in document form count as observed data — they are not assumptions just because they came from outside the project.

4. **Build the sizing model.** Express the calculation as an explicit formula. Each input must be sourced or marked as an assumption. Example: `TAM = urban_households × smartphone_penetration × annual_spend_per_user`. Show the arithmetic step by step so the logic is auditable. Include intermediate calculations (e.g., "urban households = 100M × 65% urbanization = 65M") rather than only the final number. For multi-segment markets, build per-segment estimates and sum them — this makes assumptions per segment explicit rather than hiding them in an aggregate.

5. **Define TAM, SAM, SOM.**
   - **TAM**: total demand if 100% of the addressable market were captured with no constraints. This is the broadest possible view of the opportunity.
   - **SAM**: the portion of TAM reachable with current business model, geography, or channel constraints. SAM answers: "given how we operate today, what slice can we actually serve?"
   - **SOM**: realistic share of SAM capturable given competition, go-to-market capacity, and time horizon. SAM filters TAM by feasibility; SOM filters SAM by competitiveness. The SOM should reflect a time-bound target (e.g., "within 3 years") rather than an indefinite horizon.

6. **Run sensitivity analysis.** Identify the 3–5 assumptions with the largest impact on the estimate. Vary each by ±20% and report the resulting TAM/SAM/SOM range. Rank assumptions by impact. If a single assumption swings the result by more than 40%, flag it as the critical uncertainty and recommend it be validated first. For each assumption, note whether the relationship is linear (impact scales proportionally) or nonlinear (small input change produces large output change) — nonlinear effects deserve stronger caveats.

7. **Cross-validate.** Check the estimate against at least one independent benchmark: per-capita spending, comparable market share ranges, or published industry figures. If the estimate implies unreasonable market share (>50% in fragmented markets) or implausible per-capita spending, flag the inconsistency explicitly. A cross-validation failure does not invalidate the estimate but signals that an assumption may need recalibration. For bottom-up estimates, compare against a top-down reference figure if available, or vice versa.

8. **Document uncertainty.** Label every model input with its source type and confidence:
   - **Observed**: drawn directly from a data file or published source with a traceable reference. Highest confidence.
   - **Estimated**: derived from research, with stated methodology and source. Medium confidence.
   - **Assumed**: judgment call or placeholder. Lowest confidence. These carry the highest uncertainty and are the primary targets for sensitivity analysis.

9. **State change conditions.** For each key assumption, describe: under what conditions would it be wrong, and how would the estimate shift (direction and approximate magnitude)? This gives the user a framework for updating the model as new data arrives and prevents the estimate from being treated as static. Example: "If smartphone penetration is actually 55% instead of 65%, TAM drops by ~15%. This would occur if rural adoption grows slower than forecast."

10. **Produce the output.** Assemble the sizing summary, methodology statement, inputs table, sensitivity analysis, sensitivity chart, cross-validation notes, caveats, and recommendation into the output contract format below. Use `$chart-rules` for any visualizations.

## Output Contract

- **Sizing summary.** TAM, SAM, SOM as low/base/high ranges. One paragraph explaining the methodology choice and why it was selected over alternatives. State the most important driver of the estimate and whether the opportunity appears large enough to justify further investment.
- **Methodology statement.** Which approach was used (top-down, bottom-up, analog) and why it fits the available data. If multiple approaches were feasible, note which was chosen and why the alternatives were set aside.
- **Model formula.** The explicit formula with all inputs named in a single line. Show intermediate calculations step by step so the reader can follow the arithmetic from raw inputs to the final estimate without needing to open a separate file.
- **Model inputs table.** Each input: name, value, source type (observed/estimated/assumed), confidence (high/medium/low), and source reference (filename or publication). Sort by confidence ascending so the weakest inputs appear first.
- **Sensitivity table.** Top 3–5 assumptions: base value, low/high range (±20%), impact on TAM (absolute and percentage). Ordered by impact descending.
- **Sensitivity chart.** Tornado chart or horizontal bar chart showing TAM range under ±20% assumption variation. Follow `$chart-rules`.
- **Cross-validation notes.** Sanity checks performed, benchmark comparisons, per-capita or market-share reasonableness assessment. State which checks passed and which raised flags.
- **Caveats and uncertainty.** What is unknown, which assumptions are weakest, which data would reduce uncertainty most if obtained. Be specific: "we do not know market share in region X" rather than "the estimate is uncertain." If the model chains multiple assumptions, flag compound uncertainty explicitly.
- **Recommendation.** What this sizing means for the business decision. Is the opportunity large enough to pursue? Which assumption should be validated next before committing resources? State the most valuable next data-gathering step (e.g., "survey 200 target customers to narrow ARPU assumption").

## Methodology Selection Guidance

Choose the approach that best matches the available data. When multiple approaches are viable, prefer the one that relies most heavily on observed data and least on assumptions.

- **Bottom-up preferred when**: you have customer counts, transaction volumes, unit pricing, or demographic data in project files. Bottom-up estimates are easier to audit and update because each input is a discrete, testable number.
- **Top-down preferred when**: reliable industry reports or government statistics are available and unit-level data is sparse. Top-down works well for early-stage sizing but carries risk of inherited error from report assumptions.
- **Analog preferred when**: neither bottom-up nor top-down data exists for the target market, but a structurally similar market has known figures. The analog must be explicitly named and each adjustment factor must be stated.

Do not mix methodologies within the same estimate without noting which parts came from which approach and why.

## Assumption Ground Rules

Market sizing always requires assumptions. The goal is not to eliminate them but to make them explicit, bounded, and auditable.

- **Every assumption must have a stated rationale.** "We assume 10% annual growth" is insufficient. "We assume 10% annual growth based on the 3-year CAGR from industry report X (2023-2025)" is acceptable.
- **Default assumptions are not allowed.** Do not use generic defaults (e.g., "standard 5% discount rate") without connecting them to the specific market context.
- **Directional assumptions are cheaper than magnitude assumptions.** "Penetration will increase" is easier to defend than "penetration will be exactly 34%." If you cannot source a precise number, state the expected direction and give a plausible range.
- **Compound assumptions multiply uncertainty.** When a model chains three assumptions (e.g., population × penetration × spend), each at ±20% uncertainty, the combined range can be wide. Flag compound uncertainty explicitly and recommend which assumption to tighten first.
- **Assumptions the user provides are still assumptions.** If the user says "assume 5% market share," record it as user-assumed, not observed. It should still appear in the sensitivity analysis.
- **Archive the model.** Save the sizing model as a reproducible artifact (Python script or spreadsheet) in the workspace so it can be updated when new data arrives. Include all formulas, inputs, and source references. A market sizing without a reusable model is a one-time opinion.

## Skill Dependencies

- `$chart-rules`: For sensitivity tornado charts and TAM/SAM/SOM visualizations
- `$analyze-data-quality`: If source market data quality is questionable or inputs are derived from user-provided files that need profiling before use

## Quality Bar

Before signing off, confirm all eight checks. If any check fails, fix before delivery:

1. Market scope is clearly defined: geography, customer segment, time horizon, and unit stated in the sizing summary.
2. Methodology choice is explained: which approach (top-down, bottom-up, analog) was used and why it fits the available data.
3. Every model input is labeled with source type: observed (from a file or published reference), estimated (from research with stated method), or assumed (judgment call). No input lacks a source label.
4. TAM > SAM > SOM relationship is logically consistent. Each filter from TAM to SAM to SOM has a stated constraint (geography, channel, competition, time).
5. Sensitivity analysis covers the top 3–5 most impactful assumptions. Each varied ±20% with impact on the headline estimate reported in both absolute and percentage terms.
6. At least one independent cross-validation check performed: per-capita comparison, market share reasonableness, or benchmark against a published figure. Both passes and flagged concerns are reported.
7. Uncertainty is communicated as ranges, not point estimates. Low/base/high values are stated for TAM, SAM, and SOM. The range between low and high should not exceed 3× unless explicitly justified.
8. The recommendation is tied to the sizing output: it states whether the opportunity is large enough, which assumption most needs validation, and what the next data-gathering step should be.

After delivery: archive the model as a reusable artifact so the estimate can be refreshed when new data arrives.

## Available Tools

- `preflight.py`：项目预检信封
- `validation.py`：验证门
- `execution.py`：本地 Python 代码执行
