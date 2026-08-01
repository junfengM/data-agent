# Contributing to Data Agent

Thanks for contributing. This project is a local-first, skill-driven data
analysis agent workbench. The LLM plans, routes, interprets, and assembles;
deterministic tools compute, validate, render, and export.

## Development setup

```bash
# Backend (Python 3.12, uv recommended)
cd server
uv sync --extra dev
cp ../config/models.example.yaml ../config/models.yaml
cp .env.example .env

# Frontend and desktop
cd ../apps/web && bun install
cd ../apps/desktop && bun install
```

API keys are required only for real-model runs. The mock demo and test suite
run without them.

## Validation before opening a PR

```bash
./scripts/test-server            # backend compile + pytest
cd apps/web && bun run test && bun run build
cd apps/desktop && bun run test && bun run build
git diff --check
```

Recorded baseline: server `787` tests, web `51`, desktop `8`.

## Code conventions

- Keep analysis context project-scoped; do not add global business-background
  memory.
- Deterministic tools compute, validate, render, and export; the LLM plans,
  routes, interprets, and assembles.
- Chinese-first UI; module-based components.
- New chart/report block types need a reviewed renderer before the LLM can
  select them — no arbitrary runtime HTML/CSS/React.
- Add a regression test with every bug fix.
- Run `cd server && uv run ruff check app && uv run mypy app` before submitting
  backend changes (these are CI gates).

## Branching and commits

- Use short-lived feature branches: `feat/<name>`.
- Commit logically and keep the working tree reviewable.
- Do not force-push to `main`; pull with rebase before pushing.
- Never commit `workspace/`, `server/.env`, `config/models.yaml`, build output,
  or lockfile churn unrelated to your change.

## Docs

Public documentation lives in `README.md` and `docs/`. If a change affects
architecture, validation behavior, evidence semantics, or tool contracts,
update the matching doc in the same PR.
