# Data Agent

Local-first, skill-driven data analysis agent harness inspired by Codex and Data Analytics workflows.

## MVP Scope

- Local Web App: React + Vite
- Backend: FastAPI
- Model providers: OpenAI and DeepSeek through OpenAI-compatible auth
- Data sources: CSV, Excel, and external API connectors
- Execution: local-controlled Python analysis with pandas and DuckDB
- Skills: editable Markdown workflows
- Memory: SQLite-backed analysis projects, project-scoped context, dataset schemas, runs, artifacts, and preferences
- Artifacts: visual reports (manifest + snapshot), markdown reports, HTML reports, notebooks, charts, dashboards, tables, and run logs

## Layout

```text
apps/web/        React + Vite UI
server/app/      FastAPI backend and agent harness
skills/          Editable analysis skills
config/          Example model and app configuration
workspace/       Local uploads, runs, and artifacts
```

## Direction Documents

Start here when handing the project to another agent:

- [Agent Handoff](docs/agent-handoff.md) — current project background, latest progress, active architecture, and known follow-ups.

Supporting direction documents:

- [Project Consensus](docs/consensus.md)
- [Recommended Plan](docs/roadmap.md)
- [Visual Report Architecture](docs/visual-report-architecture.md)
- [Project Progress](docs/progress.md)
- [Review Log](docs/reviews.md)
- [Tool Contracts](docs/tool-contracts.md)

Community documents:

- [Contributing](CONTRIBUTING.md)
- [Security Policy](SECURITY.md)
- [License](LICENSE) (MIT)

## Quick Start

Backend:

```bash
# Recommended: uv (see server/uv.lock)
cd server
uv sync --extra dev
cp ../config/models.example.yaml ../config/models.yaml
cp .env.example .env
uvicorn app.main:app --reload --port 8787

# Alternative: plain virtualenv
cd server
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp ../config/models.example.yaml ../config/models.yaml
cp .env.example .env  # set DATA_AGENT_GENERATED_CODE_EXECUTION=local-dev
uvicorn app.main:app --reload --port 8787
```

Run tests:

```bash
./scripts/test-server
```

Frontend:

```bash
cd apps/web
npm install
npm run dev
```

## macOS Desktop App (Self-Use)

The first desktop target is a real macOS app shell that loads the built React UI
and starts the local FastAPI backend automatically. This self-use build depends
on the repository-local backend virtualenv at `server/.venv`.

Prepare the backend:

```bash
cd server
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp ../config/models.example.yaml ../config/models.yaml
cp .env.example .env
```

Install and run the desktop app:

```bash
cd apps/desktop
npm ci
bun run build:web
bun run start
```

If Electron's binary download stalls or fails on the local network, rebuild it
through the npm mirror:

```bash
cd apps/desktop
ELECTRON_MIRROR=https://npmmirror.com/mirrors/electron/ npm rebuild electron
```

Package a local macOS app:

```bash
cd apps/desktop
bun run dist:mac
```

If the app is launched outside the repository layout, set
`DATA_AGENT_REPO_ROOT=/path/to/data_agent` before starting it. The distributable
macOS version will later package or provision Python dependencies instead of
depending on `server/.venv`.

## Execution Mode

The agent runs LLM-generated Python code through a configurable runner.  
`DATA_AGENT_GENERATED_CODE_EXECUTION` in `server/.env` controls the mode:

**Execution disabled (default, safe):**
- Set `DATA_AGENT_GENERATED_CODE_EXECUTION=disabled`
- Generated code does not execute
- Runs return a blocked result explaining that execution must be enabled

**Local development execution:**
- Set `DATA_AGENT_GENERATED_CODE_EXECUTION=local-dev` (or `local` for backward compatibility)
- Uses `sys.executable` with scrubbed environment variables
- Output collected in run directory only
- **local-dev is not a security boundary.** Do not enable it for untrusted users, shared servers, or production. Generated code runs as a local subprocess on the host with no filesystem or network isolation. It can read host-accessible files and make network requests. `HOME` is redirected to a per-run directory and `PYTHONPATH` is cleared before subprocess execution.
- For untrusted code or data, use `disabled` mode and review generated code manually.

**Sandbox execution (future):**
- Set `DATA_AGENT_GENERATED_CODE_EXECUTION=sandbox`
- Currently returns a clear error: no sandbox backend is configured
- Requires deployment of a real container/VM sandbox backend

**Supported modes: `disabled`, `local-dev`, legacy `local` alias, and `sandbox` placeholder.** Docker-based execution has been removed.

The backend now supports full analysis workflows: upload data, route to a skill, run analysis code with evidence gathering, produce structured report artifacts with charts and tables, and export artifact packages.

## Quarto (Optional)

Quarto is an external CLI dependency used to generate polished Web Report HTML artifacts.  
**Web Report requires Quarto.** If Quarto is unavailable, the main analysis still succeeds and Web Report is skipped.

### Install Quarto

**Option 1 — System install:**
```bash
brew install quarto          # macOS
# or download from https://quarto.org/docs/download/
```

**Option 2 — Explicit binary path:**
```bash
export DATA_AGENT_QUARTO_BIN=/path/to/quarto
```

**Option 3 — Managed install (downloads a fixed version to ~/.cache/):**
```bash
./scripts/install-quarto       # default: 1.9.38
./scripts/install-quarto 1.9.38
```
This script downloads from GitHub releases, verifies the SHA-256 checksum, and installs under `~/.cache/data-agent/quarto/<version>/`. The runtime detector finds it automatically.

### Runtime detection

`DATA_AGENT_QUARTO_BIN` wins when set. Otherwise, the runtime detector checks:
1. Managed path: `~/.cache/data-agent/quarto/<DATA_AGENT_QUARTO_VERSION>/bin/quarto`
2. System PATH: `quarto`

No automatic download happens at startup (`DATA_AGENT_QUARTO_AUTO_INSTALL` defaults to `false`).

## License

Released under the [MIT License](LICENSE).
