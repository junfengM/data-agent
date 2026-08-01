# Security Policy

## Local execution is not a sandbox

Generated analysis code runs through the `local-dev` execution mode as a local
subprocess on the host. This is a development convenience, **not** a security
boundary:

- Generated code can read host-accessible files.
- Generated code can make network requests.
- Output limits cap discovered artifacts, but do not prevent files from being
  created.

Do not enable `local-dev` for untrusted users, shared servers, or production.
For untrusted code or data, keep execution in `disabled` mode (the default) and
review generated code manually. A real sandbox backend is a planned future
work item, not a current feature.

## API keys and local configuration

- API keys live only in `server/.env` and `config/models.yaml`, which are
  gitignored and never committed.
- Example configuration is provided by `.env.example` and
  `config/models.example.yaml` with empty placeholders.
- The desktop app reads the same local configuration; it never transmits keys
  outside the local backend.

## Local data and trace privacy

- Uploaded datasets, project context, runs, and generated artifacts are stored
  under the gitignored `workspace/` directory.
- Planner events persist bounded prompt snapshots (previews, tool arguments,
  context budgets) to the local SQLite store for the LLM tuning view.
  Since 2026-08-01 prompt snapshots are **not persisted by default**; set
  `DATA_AGENT_TRACE_PERSIST_PROMPT_SNAPSHOTS=true` in `server/.env` to opt in.
  Export redacts local paths and secret-like keys, but always review exported
  trace or report files before sharing them.

## Reporting a vulnerability

Please do not open a public issue for a security vulnerability. Report it by
opening a private GitHub issue, or contact the maintainers directly if one is
listed on the repository profile. Include:

- Affected version or commit;
- A minimal reproduction (data shape and steps, no sensitive data);
- Expected vs. observed behavior.

We aim to acknowledge reports within 5 business days and to ship a fix with a
regression test.
