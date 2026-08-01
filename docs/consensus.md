# Project Consensus

This project is a local-first data analysis agent harness inspired by Codex and the Data Analytics plugin.

## Why Build This

The current workflow already works in ChatGPT web:

1. Prepare business background and analysis context.
2. Upload an Excel or CSV file.
3. Ask ChatGPT to analyze the data.
4. Generate a Markdown report.
5. Convert Markdown to HTML.
6. Prepare visuals for sharing or presentation.

The pain is not that the web workflow cannot analyze data. The pain is that the workflow is manual, repeated, and hard to control.

This project should turn that proven manual workflow into a reusable local agent workbench.

Important clarification: background context is not one unified global prompt. Different analysis projects can and should have different background, metric definitions, reporting preferences, audiences, and historical runs.

## Core Direction

The first version should fully reference the thinking behind Codex/Data Analytics:

- skill-driven workflows
- manifest-declared agent capabilities
- source-backed analysis
- deterministic tool execution
- semantic-layer-backed business definitions
- persistent context and memory
- artifact-based outputs
- validation gates before delivery
- controllable report and visualization structure

The goal is not to copy implementation details. The goal is to adopt the operating model: what counts as a good analysis, how analysis steps are governed, and how outputs are made reproducible and presentable.

## What This Is

Data Agent is:

- a local Web App
- a data analysis agent harness
- a Codex-like workbench for analysis
- a tool that keeps project context and metric definitions
- a system that generates Markdown, HTML, notebook, chart, table, dashboard, and run-log artifacts

## What This Is Not

Data Agent is not:

- just a chatbot around pandas
- just an Excel upload demo
- a free-form Markdown generator
- a random chart generator
- a full BI platform in the first version

## Product Principles

1. Context should be persistent and project-scoped.

   Users should not need to paste the same business background every time for the same analysis project. Each project should have its own context package: business background, metric definitions, preferences, historical analyses, common datasets, and caveats. A run should use the selected project's context, not a universal global context.

2. Skills should govern the workflow.

   Different analysis tasks should route to different skill workflows, such as KPI reporting, metric diagnostics, product analysis, visualization, report generation, and dashboard generation.

3. Tools should do deterministic work.

   The model should plan and synthesize. Python, DuckDB, file readers, chart renderers, and exporters should perform the actual computation and artifact generation.

   In this agent, the LLM is the cognitive orchestration layer, not the calculator of record. Its responsibilities are:

   - recognize analytical intent and route to the right primary and auxiliary skills
   - judge whether project-scoped context is sufficient, and surface missing definitions or caveats
   - generate bounded, inspectable analysis plans
   - decide which deterministic tools should be called
   - constrain open-ended exploration by proposing, scoring, and selecting analysis angles
   - interpret tool outputs into business meaning without inventing unsupported claims
   - assemble structured report blocks that connect claims to table/chart evidence
   - perform quality checks for data limitations, weak evidence, metric ambiguity, chart misuse, and overclaiming

   The LLM must not silently replace deterministic computation, invent metrics, assume global business context, or present conclusions without source-backed evidence.

4. Artifacts should be first-class.

   Results should not be trapped inside chat messages. Reports, charts, dashboards, notebooks, tables, and run logs should be structured artifacts that the UI can render, inspect, and export.

5. Visualization should be controlled.

   Chart choice, report layout, table format, dashboard cards, titles, units, metric definitions, and caveats should follow explicit rules instead of being fully left to model randomness.

6. Semantic meaning should be explicit.

   Business definitions should not live only in prose. Reusable metrics, dimensions, grains, filters, joins, source precedence, and caveats should be represented in a project-scoped semantic layer so future runs can reuse and inspect them.

7. Validation should gate delivery.

   Before a run is treated as complete, the system should check that important claims have evidence, artifacts render, chart rules are followed, metric definitions are clear, and caveats/source metadata are visible.

8. Real usage should guide refinement.

   The first phase should implement the Codex/Data Analytics-inspired foundation. After real use begins, workflows, templates, chart rules, and memory behavior should be refined based on actual needs.

## Success Definition For The First Phase

The first phase is successful when a user can:

1. configure OpenAI or DeepSeek auth
2. create multiple analysis projects, each with its own background and analysis context
3. upload CSV or Excel data
4. ask an analysis question
5. have the system choose or apply a skill
6. inspect data-backed evidence
7. receive Markdown, HTML, notebook, chart/table, and dashboard-like artifacts
8. see caveats, source metadata, and reproducible run logs
