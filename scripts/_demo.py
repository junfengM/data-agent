#!/usr/bin/env python3
"""Local E2E demo — exercises the full analysis loop.

Scenario:
  1. Create analysis project
  2. Upload demo CSV dataset
  3. Configure project context
  4. Create and select semantic layer
  5. Run analysis with deterministic mock planner
  6. Inspect visual report artifact (manifest, evidence, validation)
  7. Validate export package integrity

Usage: ./scripts/demo
"""
import csv
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "server"))

import anyio  # noqa: E402

# ── Inline mock planner (duplicated from tests to keep demo standalone) ──

_MOCK_REPORT_MD = """## Monthly Revenue Analysis

### Summary
Revenue grew 16.3% from Jan to Mar 2024, driven primarily by Electronics.

### Key Findings
- **Electronics** led revenue growth with a 23.3% increase.
- **Clothing** showed steady month-over-month performance.
- **Food** category grew 20% driven by increasing order volume.

### Evidence
The analysis used 3 months of sales data (Jan-Mar 2024) across 3 product categories.

### Caveats
- Only 3 months of data available
- Only 3 product categories represented
"""

_MOCK_ANALYSIS_CODE = (
    "import pandas as pd\n"
    "\n"
    "data_path = dataset_paths[0]\n"
    "df = pd.read_csv(data_path)\n"
    "\n"
    "monthly = df.groupby('month')['revenue'].sum().reset_index()\n"
    "monthly.to_csv('monthly_revenue.csv', index=False)\n"
    "\n"
    "print('Chart: monthly_revenue_trend — monthly revenue increased from Jan to Mar')\n"
    "print(f'  Source: demo_sales.csv, {len(monthly)} rows')\n"
    "print('  Key finding: Revenue grew 16.3% from Jan to Mar 2024')\n"
    "print('Analysis complete')\n"
)


def _make_mock_planner():
    """Return (mock_init, mock_run_analysis) for monkeypatching Planner."""

    def mock_init(self, model_config):
        self.config = model_config
        self.index_content = ""

    async def mock_run_analysis(
        self,
        question,
        preflight_markdown,
        profiles,
        project_contexts=None,
        ad_hoc_context=None,
        skill_registry=None,
        code_executor=None,
        finding_saver=None,
        require_evidence=True,
    ):
        if code_executor:
            await code_executor(
                _MOCK_ANALYSIS_CODE,
                "monthly_revenue_analysis",
                "Compute monthly revenue totals and create a native visual-report chart spec",
            )

        if finding_saver:
            await finding_saver(
                "monthly_revenue",
                "SUM(revenue)",
                "sum",
                "month",
                "revenue",
                "Based on 3 months of data (Jan-Mar 2024)",
                "demo_sales.csv",
            )

        return {
            "report_md": _MOCK_REPORT_MD,
            "title": "Monthly Revenue Analysis",
            "summary": "Revenue grew 16.3% from Jan to Mar 2024",
            "selected_skills": ["product-analysis"],
            "chart_specs": [
                {
                    "name": "monthly_revenue_trend",
                    "chart_type": "line",
                    "intent": "trend",
                    "x_field": "month",
                    "y_fields": ["revenue"],
                    "title": "Monthly Revenue Trend",
                }
            ],
            "candidate_angles": [
                {
                    "id": "angle_001",
                    "question": "What is the monthly revenue trend?",
                    "dimensions": ["month"],
                    "measures": ["revenue"],
                    "expected_evidence": "line chart, monthly aggregation",
                    "impact_score": 0.8,
                    "confidence_score": 0.9,
                    "actionability_score": 0.7,
                    "novelty_score": 0.3,
                    "relevance_score": 1.0,
                    "data_sufficiency_score": 0.8,
                    "selected": True,
                    "rejected_reason": None,
                },
                {
                    "id": "angle_002",
                    "question": "Which product category has highest revenue?",
                    "dimensions": ["category"],
                    "measures": ["revenue"],
                    "expected_evidence": "bar chart, category aggregation",
                    "impact_score": 0.6,
                    "confidence_score": 0.7,
                    "actionability_score": 0.5,
                    "novelty_score": 0.4,
                    "relevance_score": 0.7,
                    "data_sufficiency_score": 0.7,
                    "selected": False,
                    "rejected_reason": "Lower priority than trend analysis",
                },
            ],
            "caveats": [
                "Only 3 months of data available",
                "Only 3 product categories represented",
            ],
            "next_checks": [
                "Break down revenue by product category",
                "Extend to more months",
            ],
        }

    return mock_init, mock_run_analysis


# ── Helpers ─────────────────────────────────────────────────────────────

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


# ── Main demo ───────────────────────────────────────────────────────────

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
    from app.tools.preflight import load_semantic_layer

    print("=" * 60)
    print("  Data Agent — Local E2E Demo")
    print("=" * 60)

    workspace = tempfile.mkdtemp(prefix="data-agent-demo-")
    workspace_dir = Path(workspace)
    print(f"\n[1/7] Workspace: {workspace_dir}")

    csv_path = workspace_dir / "demo_sales.csv"
    create_demo_csv(csv_path)
    print(f"[2/7] Demo dataset: {csv_path.name} ({csv_path.stat().st_size} bytes)")

    store = MemoryStore(workspace_dir / "demo.db")
    print("[3/7] Memory store: SQLite")

    proj = store.create_project(
        AnalysisProjectCreate(
            name="Demo Sales Analysis",
            description="E2E demo project",
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
    print("  Running analysis...")
    print("-" * 60)

    # Patch Planner to use deterministic mock (self-contained, no test imports)
    import app.agent.planner as planner_mod
    mock_init, mock_run = _make_mock_planner()
    orig_init = planner_mod.Planner.__init__
    orig_run = planner_mod.Planner.run_analysis
    planner_mod.Planner.__init__ = mock_init
    planner_mod.Planner.run_analysis = mock_run

    # Create minimal model config
    config_dir = workspace_dir / "config"
    config_dir.mkdir()
    import os
    import yaml
    (config_dir / "models.yaml").write_text(yaml.dump({
        "default_model": "mock-model",
        "models": {
            "mock-model": {
                "provider": "openai_compatible",
                "base_url": "http://localhost",
                "api_key_env": "MOCK_KEY",
                "model": "mock-model",
                "temperature": 0.2,
                "max_tokens": 4096,
            }
        }
    }))
    os.environ["MOCK_KEY"] = "mock-api-key"

    orch = AgentOrchestrator(
        skills_dir=PROJECT_ROOT / "skills",
        workspace_dir=workspace_dir,
        config_dir=config_dir,
        store=store,
        generated_code_execution="local",
    )

    request = AnalysisRequest(
        question="What is the monthly revenue trend?",
        project_id=proj.id,
        dataset_ids=[dataset_id],
    )

    run = await orch.run(request)
    store.record_run(run)
    planner_mod.Planner.__init__ = orig_init
    planner_mod.Planner.run_analysis = orig_run

    print(f"\n  Run ID:    {run.id}")
    print(f"  Status:    {run.status}")
    print(f"  Skill:     {run.skill_id}")

    print(f"\n  Artifacts ({len(run.artifacts)}):")
    for a in run.artifacts:
        print(f"    [{a.type}] {a.title}")

    print(f"\n  Tool calls ({len(run.tool_calls)}):")
    for tc in run.tool_calls:
        print(f"    {tc.name}: {tc.status}")

    manifest_arts = [a for a in run.artifacts if str(a.type) == "visual_report"]
    ok = True
    data = None
    manifest = None
    if manifest_arts:
        data = manifest_arts[0].data
        manifest = data["manifest"]
        blocks = manifest["blocks"]
        charts = manifest["charts"]
        print(f"\n  Visual Report: {len(blocks)} blocks, {len(charts)} charts, "
              f"{len(manifest['tables'])} tables, {len(manifest['sources'])} sources")
        blocks_with_ev = [b for b in blocks if b.get("evidence_ids")]
        print(f"  Evidence:  {len(blocks_with_ev)} blocks with evidence_ids")
    else:
        ok = False
        print("\n  Visual Report: MISSING")

    for rl in run.artifacts:
        if str(rl.type) == "run_log" and rl.data and "validation_results" in rl.data:
            vr = rl.data["validation_results"]
            passed = sum(1 for v in vr if v.get("passed"))
            print(f"\n  Validation: {passed}/{len(vr)} gates passed")
            for v in vr:
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

    if data is None or manifest is None:
        print("\n  Export: skipped because visual report is missing")
        return 1

    manifest_obj = ArtifactManifest.model_validate(manifest)
    snapshot_obj = ArtifactSnapshot.model_validate(data["snapshot"])

    export_path = export_artifact_package(
        run_id=run.id,
        title="Demo Sales Analysis",
        question=run.question,
        project_id=proj.id,
        manifest=manifest_obj,
        snapshot=snapshot_obj,
        output_dir=export_dir,
    )
    print(f"\n  Export: {export_path.name} ({export_path.stat().st_size} bytes)")

    result = validate_exported_package(export_path)
    print(f"  Integrity: {'VALID' if result.valid else 'INVALID'}")
    for w in result.warnings:
        print(f"    WARN: {w}")

    if sl_path.exists():
        sl = load_semantic_layer(sl_path)
        print(f"\n  Semantic Layer post-run: {len(sl.metrics)} metric(s)")
        for m in sl.metrics[:5]:
            agg = m.get("aggregation", "?")
            prov = m.get("provenance", {})
            run_ref = prov.get("run_id", "?")[:8] if prov.get("run_id") else "?"
            print(f"    - {m['name']}: {agg} (run: {run_ref})")

    ok = ok and result.valid and run.status in ("completed", "completed_with_warnings")
    print("\n" + "=" * 60)
    print(f"  {'PASS' if ok else 'FAIL'}")
    print(f"  Status:   {run.status}")
    print(f"  Export:   {'valid' if result.valid else 'invalid'}")
    print(f"  Workspace: {workspace_dir}")
    print("=" * 60)

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(anyio.run(demo))
