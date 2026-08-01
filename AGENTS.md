# AGENTS.md

Data Agent is a local-first, skill-driven data analysis agent workbench. The
LLM plans, routes, interprets, and assembles; deterministic tools compute,
validate, render, and export.

## Architecture at a glance

- `server/app/agent/` — orchestration, planner, visual report assembly, run
  artifacts, validation wiring.
- `server/app/tools/` — deterministic tools: execution guard, preflight,
  semantic layer, evidence, validation, exports.
- `server/app/api/` — FastAPI routes (runs, datasets, projects, trace).
- `apps/web/` — React + Vite UI (Chinese-first).
- `apps/desktop/` — Electron shell that loads `apps/web` and starts the local
  backend.
- `skills/`, `templates/` — editable Markdown skills and report templates.
- `config/` — example model config, skill routing, semantic-layer schema.

## Non-negotiables

- Keep analysis context project-scoped; no global business-background memory.
- Deterministic tools compute, validate, render, and export; the LLM plans,
  routes, interprets, and assembles.
- Artifacts are first-class (visual reports, Markdown/HTML reports, notebooks,
  charts, tables, run logs).
- Key claims trace to evidence: tables, charts, sources, or explicit caveats.
- No arbitrary runtime HTML/CSS/React: visualization is schema/contract driven.
- `local-dev` execution is a development convenience, not a security sandbox.

## Validation

```bash
./scripts/test-server
cd apps/web && bun run test && bun run build
cd apps/desktop && bun run test && bun run build
git diff --check
```

See `CONTRIBUTING.md` for setup details and `SECURITY.md` for trust boundaries.
