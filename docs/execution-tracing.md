# Execution Tracing

Normal Agent runs now persist a detailed event timeline in SQLite. The in-app
`任务回放` module reads these events while a task is still running and can export
one AI-readable JSON diagnostic package.

The runtime trace includes:

- project, dataset profile, and preflight stages;
- every LLM request and response with duration, message size, available tools,
  requested tools, and provider token usage when available;
- planner tool request, result, malformed-argument failure, feedback repair, and
  forced-finalization events;
- generated analysis code, execution stdout/stderr summaries, tables, and charts;
- report generation, validation, artifacts, sources, and evidence links.

Generated code is persisted because it is required for detailed diagnosis. Hidden
model reasoning is not recorded.

## In-App Export

Open `任务回放`, select a run, and click `导出 AI 诊断包`. The download endpoint is:

```text
GET /api/runs/<run_id>/trace/export
```

The JSON package contains the final run snapshot, diagnostic summary, chronological
runtime events, and a derived artifact/evidence trace. Keys that look like API keys,
credentials, passwords, secrets, authorization headers, or tokens are removed.

Historical runs created before runtime event persistence still export their final
run snapshot and derived artifact trace, but cannot reconstruct missing LLM timing
events.

## Standalone Runner

Use `scripts/trace-run` when a separate command-line trace is needed without using
the normal UI workflow.

The trace runner wraps the OpenAI-compatible client used by the planner, captures orchestrator events, records LLM call timings and token usage when the provider returns `usage`, and saves errors with stage, error type, message, and a truncated traceback.

## Usage

```bash
./scripts/trace-run \
  --question "分析一下本周销售变化" \
  --project-id <project_id> \
  --dataset-id <dataset_id>
```

Multiple datasets:

```bash
./scripts/trace-run \
  --question "What stands out in these datasets?" \
  --dataset-ids <dataset_id_1>,<dataset_id_2>
```

The default output path is:

```text
workspace/artifacts/<run_id>/execution_trace.json
```

For failures before a run id is available, the trace is written under:

```text
workspace/artifacts/trace-errors/
```

## Useful options

```bash
--model-config-id <id>      # choose a configured model
--skill-id <id>             # pass an initial skill id
--context "..."             # add run-specific context
--output /tmp/trace.json    # choose trace output path
--include-code              # include generated code; default records only code length
--include-llm-content       # include LLM message/content previews; may contain sensitive data
--max-string-chars 2000     # adjust per-field truncation
```

## What is recorded

- Request metadata: question, project id, dataset ids, selected model config id, skill id, and whether run-specific context is present.
- Environment metadata: config directory, workspace directory, skills directory, SQLite path, and generated code execution mode.
- Orchestrator event timeline with elapsed milliseconds.
- LLM calls: duration, model, message count, approximate prompt characters, available tools, requested tool calls, finish reason, response id, and token usage when available.
- Tool-call argument summaries: step names, generated-code character counts, evaluate-attempt payload sizes, candidate-angle counts, chart-spec counts, and semantic-finding summaries.
- Final run summary: status, selected skill, artifact count, tool calls, validation counts, and artifact metadata.
- Errors: stage, error type, message, extra context, and a truncated traceback.

## Privacy notes

By default, generated code is not included and long strings are truncated. The trace may still contain dataset ids, field names, project names, context snippets, stdout/stderr snippets from events, and report previews. Review or redact the JSON before sharing it outside your environment.

Do not share `.env` files or API keys.
