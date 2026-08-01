#!/usr/bin/env python3
"""Real LLM E2E demo — exercises the full analysis loop with actual LLM planner.

Requires: config/models.yaml with a valid model and API key.
Loads server/.env automatically for API keys.
Skips cleanly with exit 0 if no model config is found.

Usage: server/.venv/bin/python scripts/_demo_llm.py

Acceptance criteria (must ALL pass for exit 0):
1. No llm_planner tool call with status "failed"
2. At least one analysis_step completed successfully
3. validation_gate not failed
4. No validation result with passed=false AND severity="fail"
5. evidence_coverage gate passes
6. evidence_references gate passes
7. Visual report manifest has >=1 chart or table from executed analysis
8. snapshot.evidence_map has >=1 evidence entry
9. Exported package validates
10. Failed tool-call details printed to output
"""
import csv
import os
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "server"))

# Load .env if present
env_path = PROJECT_ROOT / "server" / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            key, val = key.strip(), val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val

try:
    import anyio
    import yaml
except ImportError as e:
    print(f"[SKIP] Missing dependency: {e}")
    sys.exit(0)


def load_model_config(config_dir: Path) -> dict | None:
    """Load models.yaml. Returns None if no config file or no API key."""
    config_path = config_dir / "models.yaml"
    if not config_path.exists():
        return None
    try:
        config = yaml.safe_load(config_path.read_text())
        models = config.get("models", {})
        if not models:
            return None
        first_model = next(iter(models.values()))
        api_key = first_model.get("api_key_env", "")
        if not api_key:
            return None
        if not os.environ.get(api_key):
            return None
        return config
    except Exception:
        return None


def create_demo_csv(path: Path):
    rows = [
        ("month", "product", "category", "revenue", "orders"),
        ("2024-01", "Product A", "Electronics", "120000", "45"),
        ("2024-02", "Product A", "Electronics", "135000", "52"),
        ("2024-03", "Product A", "Electronics", "148000", "58"),
        ("2024-01", "Product B", "Clothing", "85000", "120"),
        ("2024-02", "Product B", "Clothing", "92000", "135"),
        ("2024-03", "Product B", "Clothing", "88000", "128"),
        ("2024-01", "Product C", "Food", "65000", "200"),
        ("2024-02", "Product C", "Food", "72000", "215"),
        ("2024-03", "Product C", "Food", "78000", "230"),
    ]
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerows(rows)


def evaluate_acceptance(run, manifest, snapshot, tool_calls, validation_results, export_valid):
    """Evaluate all 10 acceptance criteria. Returns (passed, failures)."""
    failures: list[str] = []

    planner_failed = any(
        tc.get("name") == "llm_planner" and tc.get("status") == "failed"
        for tc in tool_calls
    )
    if planner_failed:
        failures.append("C1: llm_planner failed — real planner did not execute")

    analysis_completed = any(
        tc.get("name") == "analysis_step" and tc.get("status") == "completed"
        for tc in tool_calls
    )
    if not analysis_completed:
        failures.append("C2: no analysis_step completed — LLM did not execute analysis code")

    validation_failed = any(
        tc.get("name") == "validation_gate" and tc.get("status") == "failed"
        for tc in tool_calls
    )
    if validation_failed:
        failures.append("C3: validation_gate failed")

    hard_fail_gates = [
        v for v in validation_results
        if not v.get("passed") and v.get("severity") == "fail"
    ]
    if hard_fail_gates:
        gates = ", ".join(v.get("gate_id", "?") for v in hard_fail_gates)
        failures.append(f"C4: hard validation failures ({gates})")

    ev_coverage = next(
        (v for v in validation_results if v.get("gate_id") == "evidence_coverage"), None
    )
    if ev_coverage and not ev_coverage.get("passed"):
        failures.append("C5: evidence_coverage gate did not pass")

    ev_refs = next(
        (v for v in validation_results if v.get("gate_id") == "evidence_references"), None
    )
    if ev_refs and not ev_refs.get("passed"):
        failures.append("C6: evidence_references gate did not pass")

    charts = manifest.get("charts", [])
    tables = manifest.get("tables", [])
    if len(charts) == 0 and len(tables) == 0:
        failures.append("C7: visual report manifest has 0 charts and 0 tables — no analysis evidence produced")

    evidence_map = snapshot.get("evidence_map", {}) if snapshot else {}
    if not evidence_map:
        failures.append("C8: snapshot.evidence_map is empty — no evidence entries")

    if not export_valid:
        failures.append("C9: exported package validation failed")

    return len(failures) == 0, failures


async def demo():
    from app.agent.orchestrator import AgentOrchestrator
    from app.memory.store import MemoryStore
    from app.models.schemas import (
        AnalysisProjectCreate,
        AnalysisRequest,
        ArtifactManifest,
        ArtifactSnapshot,
        ProjectContextCreate,
    )
    from app.tools.package_integrity import validate_exported_package

    print("=" * 60)
    print("  Data Agent — Real LLM E2E Demo")
    print("=" * 60)

    config_dir = PROJECT_ROOT / "config"
    model_config = load_model_config(config_dir)
    if not model_config:
        print("\n[SKIP] No model config or API key found.")
        print("  Set up config/models.yaml with a valid model and API key.")
        print("  See config/models.example.yaml for reference.")
        return 0

    workspace = tempfile.mkdtemp(prefix="data-agent-llm-demo-")
    workspace_dir = Path(workspace)
    print(f"\n[1/7] Workspace: {workspace_dir}")

    csv_path = workspace_dir / "demo_sales.csv"
    create_demo_csv(csv_path)
    print(f"[2/7] Demo dataset: {csv_path.name} ({csv_path.stat().st_size} bytes)")

    store = MemoryStore(workspace_dir / "demo.db")
    print("[3/7] Memory store: SQLite")

    proj = store.create_project(
        AnalysisProjectCreate(
            name="LLM Demo Sales Analysis",
            description="Real LLM E2E demo",
        )
    )
    print(f"[4/7] Project: {proj.name} ({proj.id})")

    store.create_project_context(
        proj.id,
        ProjectContextCreate(
            kind="business_context",
            title="Sales Data Background",
            body="Monthly sales data for 3 categories from Jan-Mar 2024.",
        ),
    )
    ctxs = store.list_project_contexts(proj.id)
    print(f"[5/7] Context: {len(ctxs)} item(s)")

    dataset_id = store.record_dataset(csv_path, csv_path.name, "text/csv")
    print(f"[6/7] Dataset: {csv_path.name} (id: {dataset_id})")

    sl_path = workspace_dir / "semantic-layer.yaml"
    store.create_semantic_layer({
        "project_id": proj.id,
        "name": "Demo Sales Metrics",
        "path": str(sl_path),
    })
    print(f"[7/7] Semantic layer: {sl_path.name}")

    print("\n" + "-" * 60)
    print("  Running analysis with real LLM planner...")
    print("-" * 60)

    orch = AgentOrchestrator(
        skills_dir=PROJECT_ROOT / "skills",
        workspace_dir=workspace_dir,
        config_dir=config_dir,
        store=store,
        generated_code_execution="local",
    )

    request = AnalysisRequest(
        question="What is the monthly revenue trend and which category performs best?",
        project_id=proj.id,
        dataset_ids=[dataset_id],
    )

    run = await orch.run(request)
    store.record_run(run)

    print(f"\n  Run ID:    {run.id}")
    print(f"  Status:    {run.status}")
    print(f"  Skill:     {run.skill_id}")

    print(f"\n  Artifacts ({len(run.artifacts)}):")
    for a in run.artifacts:
        print(f"    [{a.type}] {a.title}")

    tool_calls_raw = [tc.model_dump(mode="json") for tc in run.tool_calls]
    print(f"\n  Tool calls ({len(tool_calls_raw)}):")
    for tc in tool_calls_raw:
        status = tc.get("status", "?")
        name = tc.get("name", "?")
        marker = ""
        if status == "failed":
            marker = "  <-- FAILED"
            output = tc.get("output_summary", "")
            if output:
                print(f"    {name}: {status}{marker}")
                print(f"      output: {output}")
                continue
        print(f"    {name}: {status}{marker}")

    manifest = {}
    snapshot = {}
    visual_report_arts = [
        a for a in run.artifacts if str(a.type) == "visual_report"
    ]
    if visual_report_arts:
        data = visual_report_arts[0].data
        manifest = data.get("manifest", {}) if data else {}
        blocks = manifest.get("blocks", [])
        charts = manifest.get("charts", [])
        tables = manifest.get("tables", [])
        snapshot = data.get("snapshot", {}) if data else {}
        print(f"\n  Visual Report: {len(blocks)} blocks, {len(charts)} charts, "
              f"{len(tables)} tables, "
              f"{len(manifest.get('sources', []))} sources")
        blocks_with_ev = [b for b in blocks if b.get("evidence_ids")]
        print(f"  Evidence:  {len(blocks_with_ev)} blocks with evidence_ids")
    else:
        print("\n  Visual Report: NOT FOUND")

    validation_results = []
    for rl in run.artifacts:
        if str(rl.type) == "run_log" and rl.data and "validation_results" in rl.data:
            validation_results = rl.data["validation_results"]
            passed = sum(1 for v in validation_results if v.get("passed"))
            print(f"\n  Validation: {passed}/{len(validation_results)} gates passed")
            for v in validation_results:
                icon = "PASS" if v.get("passed") else "FAIL"
                print(f"    [{icon}] {v.get('gate_id')}: {v.get('severity', '?')}")

    for rl in run.artifacts:
        if str(rl.type) == "run_log" and rl.data and "candidate_angles" in rl.data:
            angles = rl.data["candidate_angles"]
            sel = [a for a in angles if a.get("selected")]
            rej = [a for a in angles if not a.get("selected")]
            print(f"\n  Candidate Angles: {len(sel)} selected, {len(rej)} rejected")
            for a in sel:
                print(f"    + {a['question']}")
            for a in rej:
                print(f"    - {a['question']} ({a.get('rejected_reason', '?')})")

    from app.tools.exports import export_artifact_package
    export_dir = workspace_dir / "exports"
    export_dir.mkdir(exist_ok=True)

    manifest_obj = ArtifactManifest.model_validate(manifest) if manifest else None
    snapshot_obj = ArtifactSnapshot.model_validate(snapshot) if snapshot else None

    export_valid = False
    export_ok = manifest_obj and snapshot_obj
    if export_ok:
        export_path = export_artifact_package(
            run_id=run.id,
            title="LLM Demo Sales Analysis",
            question=run.question,
            project_id=proj.id,
            manifest=manifest_obj,
            snapshot=snapshot_obj,
            output_dir=export_dir,
        )
        print(f"\n  Export: {export_path.name} ({export_path.stat().st_size} bytes)")
        result = validate_exported_package(export_path)
        export_valid = result.valid
        print(f"  Integrity: {'VALID' if export_valid else 'INVALID'}")

    passed, failures = evaluate_acceptance(
        run, manifest, snapshot, tool_calls_raw, validation_results, export_valid,
    )

    print("\n" + "=" * 60)
    print(f"  {'PASS' if passed else 'FAIL'}")
    print(f"  Status:   {run.status}")
    if export_ok:
        print(f"  Export:   {'valid' if export_valid else 'invalid'}")
    if failures:
        print(f"\n  Failures:")
        for f in failures:
            print(f"    - {f}")
    print(f"  Workspace: {workspace_dir}")
    print("=" * 60)

    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(anyio.run(demo))
