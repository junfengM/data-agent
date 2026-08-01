# Test checklist

Run these checks before merging changes that touch the server, frontend, artifact manifest, validation, or execution paths.

## Server

From `server/`:

```bash
./scripts/test-server
python -m pytest \
  tests/test_execution.py \
  tests/test_package_integrity.py \
  tests/test_uploads.py \
  tests/test_semantic_validation.py \
  tests/test_evidence_linking.py
```

## Frontend

From `apps/web/`:

```bash
bun install --frozen-lockfile
bun run test
bun run build
```

If `bun install --frozen-lockfile` fails because the lockfile is stale, refresh the lockfile intentionally and include the lockfile diff in the same PR as the dependency change.

## Optional smoke and LLM checks

From `server/`:

```bash
python scripts/smoke.py
DATA_AGENT_GENERATED_CODE_EXECUTION=local python scripts/_demo_llm.py
```

The LLM demo is optional unless model credentials and local execution are configured in the test environment.
