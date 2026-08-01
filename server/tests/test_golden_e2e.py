"""Golden E2E test: exercises the full analysis loop end-to-end.

Covers: project context → dataset profile → tool execution → structured
manifest → validation → export — all with a deterministic mock planner and
a demo CSV fixture.
"""
import json
from pathlib import Path

import pytest

from app.agent.orchestrator import AgentOrchestrator
from app.memory.store import MemoryStore
from app.models.schemas import (
    AnalysisProjectCreate,
    AnalysisRequest,
    ArtifactManifest,
    ArtifactPackage,
    ArtifactSnapshot,
    ArtifactType,
    ProjectContextCreate,
)

# ── Fixture paths ──────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parents[2]
CSV_PATH = Path(__file__).parent / "fixtures" / "demo_sales.csv"

# ── Mock analysis code ─────────────────────────────────────────────────
# Runs inside the orchestrator's execute_step closure. Must load CSV,
# compute monthly revenue, save a table, and produce a bar chart.

MOCK_ANALYSIS_CODE = (
    "import pandas as pd\n"
    "import plotly.express as px\n"
    "\n"
    "# dataset_paths holds the actual file paths\n"
    "data_path = dataset_paths[0]\n"
    "df = pd.read_csv(data_path)\n"
    "\n"
    "# Aggregate monthly revenue\n"
    "monthly = df.groupby('month')['revenue'].sum().reset_index()\n"
    "monthly.columns = ['Month', 'Total Revenue']\n"
    "print('Monthly Revenue Totals:')\n"
    "print(monthly.to_string(index=False))\n"
    "\n"
    "# Save CSV table\n"
    "monthly.to_csv('monthly_revenue.csv', index=False)\n"
    "\n"
    "# Create bar chart\n"
    "fig = px.bar(monthly, x='Month', y='Total Revenue', title='Monthly Revenue Trend')\n"
    "fig.write_html('monthly_revenue_bar.html')\n"
    "print('Bar chart saved: monthly_revenue_bar.html')\n"
)

# ── Mock report markdown ───────────────────────────────────────────────
# Must mention the chart filename so manifest blocks include a chart block.

MOCK_REPORT_MD = (
    "# Monthly Revenue Analysis\n\n"
    "**Question:** What is the monthly revenue trend?\n\n"
    "## Recommendation\n\n"
    "Revenue shows steady growth across Q1 2024, reaching 314,000 in March.\n\n"
    "## Key Evidence\n\n"
    "- Total monthly revenue: 270K (Jan), 299K (Feb), 314K (Mar)\n"
    "- Revenue grew 16.3% from January to March\n"
    "- Electronics category is the largest revenue driver\n\n"
    "## Detailed Findings\n\n"
    "### Monthly Revenue Totals\n\n"
    "Monthly revenue increased each month in Q1 2024.\n\n"
    "Chart saved as monthly_revenue_bar.html shows the upward trend.\n\n"
    "## Caveats\n\n"
    "- Only 3 months of data available\n"
    "- Only 3 product categories represented\n\n"
    "## Next Steps\n\n"
    "- Extend analysis to include more months\n"
    "- Break down revenue by product category\n"
)


# ── Fixtures ───────────────────────────────────────────────────────────

@pytest.fixture
def store(tmp_path: Path) -> MemoryStore:
    return MemoryStore(tmp_path / "test.db")


@pytest.fixture
def project(store: MemoryStore) -> str:
    proj = store.create_project(
        AnalysisProjectCreate(
            name="Demo Sales Analysis",
            description="E2E golden test project",
        )
    )
    return proj.id


@pytest.fixture
def project_contexts(store: MemoryStore, project: str) -> list:
    items = []
    items.append(
        store.create_project_context(
            project,
            ProjectContextCreate(
                kind="business_context",
                title="Revenue Analysis Guidelines",
                body="Monthly revenue is the primary KPI. Always compare against previous month.",
            ),
        )
    )
    items.append(
        store.create_project_context(
            project,
            ProjectContextCreate(
                kind="data_quality_note",
                title="Data Completeness Note",
                body="Demo data covers Jan-Mar 2024. Missing data should be flagged in caveats.",
            ),
        )
    )
    return items


@pytest.fixture
def dataset_id(store: MemoryStore) -> str:
    return store.record_dataset(CSV_PATH, CSV_PATH.name, "text/csv")


@pytest.fixture
def semantic_layer_fixture(tmp_path: Path, store: MemoryStore, project: str) -> dict:
    """Create a project semantic layer YAML and register it with the store."""
    sl_yaml = tmp_path / "test-semantic-layer.yaml"
    sl_yaml.write_text("""
metrics:
  - name: monthly_revenue
    formula: SUM(revenue)
    aggregation: sum
    grain: monthly
    dimensions: [category]
    sources: [demo_sales.csv]
    caveat: Excludes refunds
    provenance:
      run_id: setup
      timestamp: "2024-01-01T00:00:00Z"
      source_dataset: demo_sales.csv
dimensions:
  - name: category
    source_column: category
    source_table: demo_sales.csv
    description: Product category
caveats:
  - description: Demo data covers Jan-Mar 2024 only
    severity: warning
    affected_metrics: [monthly_revenue]
""", encoding="utf-8")

    # Also write a copy under workspace/projects/{project_id}/ for path_safety checks
    workspace_dir = tmp_path / "workspace"
    project_sl_dir = workspace_dir / "projects" / project
    project_sl_dir.mkdir(parents=True, exist_ok=True)
    sl_workspace = project_sl_dir / "test-semantic-layer.yaml"
    sl_workspace.write_text(sl_yaml.read_text(), encoding="utf-8")

    layer = store.create_semantic_layer({
        "project_id": project,
        "name": "Demo Sales Semantic Layer",
        "path": str(sl_workspace),
    })
    return {"id": layer["id"], "name": layer["name"], "path": layer["path"]}


@pytest.fixture
def config_dir(tmp_path: Path) -> Path:
    d = tmp_path / "config"
    d.mkdir()
    (d / "models.yaml").write_text(
        "default_model: test\n"
        "models:\n"
        "  test:\n"
        "    provider: openai_compatible\n"
        "    base_url: https://test.example.com\n"
        "    api_key_env: TEST_API_KEY\n"
        "    model: test-model\n"
        "    temperature: 0.2\n"
        "    max_tokens: 4096\n"
    )
    (d / "source-category-config.yaml").write_text("categories: []\n")
    return d


@pytest.fixture
def skills_dir() -> Path:
    return REPO_ROOT / "skills"


# ── Mock helpers ───────────────────────────────────────────────────────

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
                MOCK_ANALYSIS_CODE,
                "monthly_revenue_analysis",
                "Compute monthly revenue totals and create a bar chart",
            )

        if finding_saver:
            await finding_saver(
                "monthly_revenue_trend",
                "SUM(revenue)",
                "sum",
                "month",
                "revenue",
                "Based on 3 months of data (Jan-Mar 2024)",
                "demo_sales.csv",
            )

        return {
            "report_md": MOCK_REPORT_MD,
            "title": "Monthly Revenue Analysis",
            "summary": "Revenue grew 16.3% from Jan to Mar 2024",
            "selected_skills": ["product-analysis"],
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
                    "impact_score": 0.7,
                    "confidence_score": 0.8,
                    "actionability_score": 0.6,
                    "novelty_score": 0.4,
                    "relevance_score": 0.8,
                    "data_sufficiency_score": 0.7,
                    "selected": True,
                    "rejected_reason": None,
                },
                {
                    "id": "angle_003",
                    "question": "Is there a correlation between region and revenue?",
                    "dimensions": ["region"],
                    "measures": ["revenue"],
                    "expected_evidence": "scatter plot, regional breakdown",
                    "impact_score": 0.5,
                    "confidence_score": 0.5,
                    "actionability_score": 0.4,
                    "novelty_score": 0.3,
                    "relevance_score": 0.6,
                    "data_sufficiency_score": 0.6,
                    "selected": False,
                    "rejected_reason": "Lower priority than trend and category analysis",
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


# ── Tests ───────────────────────────────────────────────────────────────

class TestGoldenE2E:
    @pytest.mark.anyio
    async def test_full_analysis_loop(
        self,
        monkeypatch,
        tmp_path,
        store,
        project,
        project_contexts,
        dataset_id,
        semantic_layer_fixture,
        config_dir,
        skills_dir,
    ):
        """Golden path through the entire orchestrator with mocked LLM."""
        from app.agent.planner import Planner

        # 1. Patch Planner to use deterministic mock
        mock_init, mock_run = _make_mock_planner()
        monkeypatch.setattr(Planner, "__init__", mock_init)
        monkeypatch.setattr(Planner, "run_analysis", mock_run)
        monkeypatch.setenv("TEST_API_KEY", "fake-key")

        # 2. Build orchestrator with local code execution
        workspace_dir = tmp_path / "workspace"
        workspace_dir.mkdir(exist_ok=True)

        orch = AgentOrchestrator(
            skills_dir=skills_dir,
            workspace_dir=workspace_dir,
            config_dir=config_dir,
            store=store,
            generated_code_execution="local",
        )

        # 3. Run analysis
        request = AnalysisRequest(
            question="What is the monthly revenue trend?",
            project_id=project,
            dataset_ids=[dataset_id],
        )
        run = await orch.run(request)

        assert run.status in ("completed", "completed_with_warnings"), (
            f"Expected 'completed' or 'completed_with_warnings', got '{run.status}'"
        )
        assert run.project_id == project

        # ── 5. visual_report artifact exists ───────────────────
        manifest_arts = [
            a for a in run.artifacts if a.type == ArtifactType.visual_report
        ]
        assert len(manifest_arts) == 1, "Expected exactly one visual_report artifact"
        data = manifest_arts[0].data
        assert data is not None

        manifest = data["manifest"]
        snapshot = data["snapshot"]

        # ── 6. manifest.blocks has chart + markdown ─────────────────
        block_types = [b["type"] for b in manifest["blocks"]]
        assert "chart" in block_types, f"Blocks missing chart type: {block_types}"
        assert "markdown" in block_types, f"Blocks missing markdown type: {block_types}"

        # ── 7. manifest.charts has bar entry ────────────────────────
        charts = manifest["charts"]
        assert len(charts) >= 1, f"Expected >=1 chart, got {len(charts)}"
        chart_type_values = [c["type"] for c in charts]
        assert "bar" in chart_type_values, f"No bar chart found: {chart_type_values}"

        # ── 8. manifest.sources has entries ─────────────────────────
        sources = manifest["sources"]
        assert len(sources) >= 1, f"Expected >=1 source, got {len(sources)}"

        # ── 9. snapshot.datasets populated ──────────────────────────
        datasets = snapshot["datasets"]
        assert len(datasets) >= 1, f"snapshot.datasets empty, got {len(datasets)} keys"

        # ── 10. validation results at top-level RunResponse ──────────
        assert len(run.validation_results) >= 1, f"Expected >=1 validation result, got {len(run.validation_results)}"
        assert run.validation_passed is not None

        # ── 10b. candidate_angles in run log ────────────────────────
        candidate_logs = [
            a for a in run.artifacts
            if a.type == ArtifactType.run_log and a.data and "candidate_angles" in a.data
        ]
        assert len(candidate_logs) >= 1, "run_log with candidate_angles must exist"
        angles = candidate_logs[0].data["candidate_angles"]
        assert len(angles) >= 1
        assert any(a["selected"] for a in angles), "No selected angle found"
        assert any(not a["selected"] for a in angles), "No rejected angle found"

        # ── 10c. selected_skills in tool_calls ──────────────────────
        planner_calls = [
            tc for tc in run.tool_calls if tc.name == "llm_planner"
        ]
        assert len(planner_calls) >= 1, "llm_planner tool call must exist"
        assert any("product-analysis" in (tc.output_summary or "") for tc in planner_calls), (
            "llm_planner output_summary missing selected skills"
        )

        # ── 10d. save_semantic_finding tool call ────────────────────
        finding_calls = [
            tc for tc in run.tool_calls if "save_semantic_finding" in tc.name
        ]
        assert len(finding_calls) >= 1, "No save_semantic_finding tool call"

        # ── 10e. evidence_ids on manifest blocks ────────────────────
        manifest_blocks = manifest["blocks"]
        blocks_with_evidence = [
            b for b in manifest_blocks if b.get("evidence_ids")
        ]
        assert len(blocks_with_evidence) >= 1, "No blocks have evidence_ids"

        # ── 10f. validation_results include severity ─────────────────
        assert any(
            hasattr(v, "severity") for v in run.validation_results
        ), "No validation result with severity field"

        # ── 10g. evidence_map in snapshot ────────────────────────────
        assert "evidence_map" in snapshot, "snapshot missing evidence_map"
        assert len(snapshot["evidence_map"]) >= 1, "evidence_map empty"
        for entry in snapshot["evidence_map"]:
            assert "id" in entry
            assert "type" in entry
            assert entry["type"] in ("table", "chart", "metric")

        # ── 10h. caveats in run log ─────────────────────────────────
        caveat_logs = [
            a for a in run.artifacts
            if a.type == ArtifactType.run_log and a.data and "caveats" in a.data
        ]
        assert len(caveat_logs) >= 1, "run_log with caveats must exist"
        assert len(caveat_logs[0].data["caveats"]) >= 1, "caveats empty"
        # ── 10i. next_checks in run log ─────────────────────────────
        assert "next_checks" in caveat_logs[0].data, "next_checks missing from run_log"
        assert len(caveat_logs[0].data["next_checks"]) >= 1, "next_checks empty"

        # ── 10j. active_semantic_layer in run log ────────────────────
        sem_logs = [
            a for a in run.artifacts
            if a.type == ArtifactType.run_log and a.data and "active_semantic_layer" in a.data
        ]
        assert len(sem_logs) >= 1, "run_log with active_semantic_layer must exist"
        sl_meta = sem_logs[0].data["active_semantic_layer"]
        assert sl_meta["id"] == semantic_layer_fixture["id"]
        assert sl_meta["name"] == semantic_layer_fixture["name"]

        # ── 10k. project identity ─────────────────────────────────────
        assert run.project_id == project

        # ── 10l. evidence_ids reference actual manifest chart/table ids
        chart_ids_in_manifest = {c["id"] for c in manifest["charts"]}
        table_ids_in_manifest = {t["id"] for t in manifest["tables"]}
        valid_ids = chart_ids_in_manifest | table_ids_in_manifest
        for b in manifest_blocks:
            for eid in b.get("evidence_ids", []):
                assert eid in valid_ids, f"evidence_id {eid} not in manifest charts/tables"

        # ── 11. Export artifact package → valid JSON ────────────────
        pkg = ArtifactPackage(
            title="Monthly Revenue Analysis",
            generated_at=manifest["generated_at"],
            project_id=project,
            question=request.question,
            manifest=ArtifactManifest.model_validate(manifest),
            snapshot=ArtifactSnapshot.model_validate(snapshot),
            metadata={"test": "golden_e2e"},
        )
        pkg_json = pkg.model_dump(mode="json")

        # Structural checks on package
        assert pkg_json["package_version"] == 1
        assert pkg_json["manifest"] == manifest
        assert pkg_json["snapshot"] == snapshot
        assert pkg_json["metadata"] == {"test": "golden_e2e"}

        # Round-trip through JSON
        json_str = json.dumps(pkg_json)
        parsed = json.loads(json_str)
        assert parsed == pkg_json

        # ── 12. Semantic layer YAML updated with confirmed metric ────
        from app.tools.preflight import load_semantic_layer

        sl_yaml_path = Path(semantic_layer_fixture["path"])
        assert sl_yaml_path.exists(), (
            f"Semantic layer YAML not found at {sl_yaml_path}"
        )
        sl = load_semantic_layer(sl_yaml_path)
        assert len(sl.metrics) >= 1, "Expected at least 1 metric in semantic layer"
        confirmed = next((m for m in sl.metrics if m["name"] == "monthly_revenue"), None)
        assert confirmed is not None, "monthly_revenue metric not found in semantic layer"
        assert confirmed.get("aggregation") != "unknown", (
            f"Expected confirmed aggregation, got '{confirmed.get('aggregation')}'"
        )
        assert "provenance" in confirmed, "Confirmed metric missing provenance"
        assert confirmed["provenance"].get("run_id") is not None, (
            "Provenance missing run_id"
        )


class TestPlannerFallback:
    @pytest.mark.anyio
    async def test_fallback_routes_metric_diagnostics_question(
        self, monkeypatch, tmp_path, store, project, dataset_id, config_dir, skills_dir
    ):
        from app.agent.planner import Planner

        async def mock_fail(self, question, **kwargs):
            step_results = []
            async def _exec(code, name, desc):
                step_results.append({"name": name, "status": "completed"})
            await _exec("", "dummy", "")
            return {
                "report_md": "",
                "title": "",
                "summary": "",
                "selected_skills": [],
                "caveats": [],
                "next_checks": [],
                "candidate_angles": [],
                "_step_results": step_results,
            }

        def mock_init(self, model_config):
            self.config = model_config
            self.index_content = ""

        monkeypatch.setattr(Planner, "__init__", mock_init)
        monkeypatch.setattr(Planner, "run_analysis", mock_fail)
        monkeypatch.setenv("TEST_API_KEY", "fake-key")

        workspace_dir = tmp_path / "workspace"
        workspace_dir.mkdir(exist_ok=True)
        orch = AgentOrchestrator(
            skills_dir=skills_dir, workspace_dir=workspace_dir,
            config_dir=config_dir, store=store,
            generated_code_execution="local",
        )
        request = AnalysisRequest(
            question="为什么销售额下降了？",
            project_id=project,
            dataset_ids=[dataset_id],
        )
        run = await orch.run(request)
        assert run.skill_id == "auto"

    @pytest.mark.anyio
    async def test_fallback_routes_kpi_weekly_question(
        self, monkeypatch, tmp_path, store, project, dataset_id, config_dir, skills_dir
    ):
        from app.agent.planner import Planner

        async def mock_fail(self, question, **kwargs):
            async def _exec(code, name, desc):
                pass
            await _exec("", "dummy", "")
            return {
                "report_md": "",
                "title": "",
                "summary": "",
                "selected_skills": [],
                "caveats": [],
                "next_checks": [],
                "candidate_angles": [],
                "_step_results": [],
            }

        def mock_init(self, model_config):
            self.config = model_config
            self.index_content = ""

        monkeypatch.setattr(Planner, "__init__", mock_init)
        monkeypatch.setattr(Planner, "run_analysis", mock_fail)
        monkeypatch.setenv("TEST_API_KEY", "fake-key")

        workspace_dir = tmp_path / "workspace"
        workspace_dir.mkdir(exist_ok=True)
        orch = AgentOrchestrator(
            skills_dir=skills_dir, workspace_dir=workspace_dir,
            config_dir=config_dir, store=store,
            generated_code_execution="local",
        )
        request = AnalysisRequest(
            question="生成本周销售周报",
            project_id=project,
            dataset_ids=[dataset_id],
        )
        run = await orch.run(request)
        assert run.skill_id == "auto"

    @pytest.mark.anyio
    async def test_planner_model_failure_marks_run_failed_and_routes_skill(
        self, monkeypatch, tmp_path, store, project, dataset_id, config_dir, skills_dir
    ):
        """Model-level planner failures (no evidence) mark the run failed and
        route the skill, without producing a normal-looking fallback report."""
        from app.agent.planner import Planner

        async def mock_raise(self, question, **kwargs):
            raise RuntimeError("no model configured for analysis")

        def mock_init(self, model_config):
            self.config = model_config
            self.index_content = ""

        monkeypatch.setattr(Planner, "__init__", mock_init)
        monkeypatch.setattr(Planner, "run_analysis", mock_raise)
        monkeypatch.setenv("TEST_API_KEY", "fake-key")

        workspace_dir = tmp_path / "workspace"
        workspace_dir.mkdir(exist_ok=True)
        orch = AgentOrchestrator(
            skills_dir=skills_dir, workspace_dir=workspace_dir,
            config_dir=config_dir, store=store,
            generated_code_execution="local",
        )
        request = AnalysisRequest(
            question="为什么销售额下降了？",
            project_id=project,
            dataset_ids=[dataset_id],
        )
        run = await orch.run(request)
        assert "metric-diagnostics" in run.skill_id
        assert run.status == "failed"
        markdown_arts = [a for a in run.artifacts if a.type == ArtifactType.markdown_report]
        assert len(markdown_arts) == 0, "Model failure must not produce a fallback report"
        assert any(
            tc.name == "llm_planner" and tc.status == "failed" for tc in run.tool_calls
        )

    @pytest.mark.anyio
    async def test_iteration_exhaustion_produces_fallback_report(
        self, monkeypatch, tmp_path, store, project, dataset_id, config_dir, skills_dir
    ):
        """Planner exhaustion returns empty report_md → orchestrator produces fallback."""
        from app.agent.planner import Planner

        async def mock_exhaustion(self, question, **kwargs):
            return {
                "report_md": "",
                "title": question[:60],
                "summary": "Analysis did not complete within iteration limit",
                "selected_skills": [],
                "caveats": ["LLM did not return a report within iteration limit"],
                "next_checks": [],
                "candidate_angles": [],
                "_step_results": [],
            }

        def mock_init(self, model_config):
            self.config = model_config
            self.index_content = ""

        monkeypatch.setattr(Planner, "__init__", mock_init)
        monkeypatch.setattr(Planner, "run_analysis", mock_exhaustion)
        monkeypatch.setenv("TEST_API_KEY", "fake-key")

        workspace_dir = tmp_path / "workspace"
        workspace_dir.mkdir(exist_ok=True)
        orch = AgentOrchestrator(
            skills_dir=skills_dir, workspace_dir=workspace_dir,
            config_dir=config_dir, store=store,
            generated_code_execution="local",
        )
        request = AnalysisRequest(
            question="帮我分析销售数据",
            project_id=project,
            dataset_ids=[dataset_id],
        )
        run = await orch.run(request)
        assert run.skill_id == "auto"
        assert run.artifacts
        planner_calls = [tc for tc in run.tool_calls if tc.name == "llm_planner"]
        assert [tc.status for tc in planner_calls] == ["failed"]

    @pytest.mark.anyio
    async def test_planner_exception_fallback_routes_to_skill_router(
        self,
        monkeypatch,
        tmp_path,
        store,
        project,
        dataset_id,
        config_dir,
        skills_dir,
    ):
        """When Planner raises, selected_skill_ids is empty → SkillRouter used."""
        from app.agent.planner import Planner

        async def mock_raise(*args, **kwargs):
            raise RuntimeError("simulated planner failure")

        def mock_init(self, model_config):
            self.config = model_config
            self.index_content = ""

        monkeypatch.setattr(Planner, "__init__", mock_init)
        monkeypatch.setattr(Planner, "run_analysis", mock_raise)
        monkeypatch.setenv("TEST_API_KEY", "fake-key")

        workspace_dir = tmp_path / "workspace"
        workspace_dir.mkdir(exist_ok=True)
        orch = AgentOrchestrator(
            skills_dir=skills_dir, workspace_dir=workspace_dir,
            config_dir=config_dir, store=store,
            generated_code_execution="local",
        )
        request = AnalysisRequest(
            question="为什么周活跃用户下降了？",
            project_id=project,
            dataset_ids=[dataset_id],
        )
        run = await orch.run(request)

        assert run.skill_id == "metric-diagnostics", (
            f"Expected metric-diagnostics, got {run.skill_id}"
        )

        report_artifact = next(
            (a for a in run.artifacts if a.type in (ArtifactType.markdown_report, ArtifactType.structured_report)),
            None,
        )
        assert report_artifact is not None
        report_content = report_artifact.content or ""
        assert "# 分析报告（自动恢复版）" in report_content, (
            f"Fallback report should use Chinese recovery title, got: {report_content[:200]}"
        )
        assert "**技能:** metric-diagnostics" in report_content, (
            f"Fallback report should include skill, got: {report_content[:200]}"
        )

        assert run.status in ("completed", "completed_with_warnings", "failed"), (
            f"Unexpected run status: {run.status}"
        )

    @pytest.mark.anyio
    async def test_golden_run_status_is_valid(
        self,
        monkeypatch,
        tmp_path,
        store,
        project,
        project_contexts,
        dataset_id,
        semantic_layer_fixture,
        config_dir,
        skills_dir,
    ):
        """Golden-path run status should be completed or completed_with_warnings."""
        from app.agent.planner import Planner

        def mock_run_no_evidence(*args, **kwargs):
            """Same as normal mock but with empty evidence_ids."""
            result = _make_mock_planner()[1](*args, **kwargs)
            # This mock still produces evidence via chart/table matching,
            # but we verify the status is correct for the golden path.
            return result

        mock_init, _ = _make_mock_planner()
        monkeypatch.setattr(Planner, "__init__", mock_init)
        monkeypatch.setattr(Planner, "run_analysis", mock_run_no_evidence)
        monkeypatch.setenv("TEST_API_KEY", "fake-key")

        workspace_dir = tmp_path / "workspace"
        workspace_dir.mkdir(exist_ok=True)
        orch = AgentOrchestrator(
            skills_dir=skills_dir, workspace_dir=workspace_dir,
            config_dir=config_dir, store=store,
            generated_code_execution="local",
        )
        request = AnalysisRequest(
            question="What is the monthly revenue trend?",
            project_id=project,
            dataset_ids=[dataset_id],
        )
        run = await orch.run(request)
        assert run.status in ("completed", "completed_with_warnings"), (
            f"Expected completed or completed_with_warnings, got {run.status}"
        )

    # ── Real LLM E2E Acceptance Predicate Tests ──

    @pytest.mark.anyio
    async def test_acceptance_planner_failed_produces_failed_run(
        self,
        monkeypatch,
        tmp_path,
        store,
        project,
        project_contexts,
        dataset_id,
        semantic_layer_fixture,
        config_dir,
        skills_dir,
    ):
        """Planner exception MUST produce run.status == 'failed', not 'completed_with_warnings'."""
        from app.agent.planner import Planner

        def mock_init(self, model_config):
            self.config = model_config
            self.index_content = ""

        async def mock_run_raise(*args, **kwargs):
            raise RuntimeError("Simulated planner failure — API key invalid")

        monkeypatch.setattr(Planner, "__init__", mock_init)
        monkeypatch.setattr(Planner, "run_analysis", mock_run_raise)
        monkeypatch.setenv("TEST_API_KEY", "fake-key")

        workspace_dir = tmp_path / "workspace"
        workspace_dir.mkdir(exist_ok=True)
        orch = AgentOrchestrator(
            skills_dir=skills_dir, workspace_dir=workspace_dir,
            config_dir=config_dir, store=store,
            generated_code_execution="local",
        )
        request = AnalysisRequest(
            question="What is the monthly revenue trend?",
            project_id=project,
            dataset_ids=[dataset_id],
        )
        run = await orch.run(request)

        # Planner failure produces failed status (hard validation failures)
        assert run.status == "failed", (
            f"Planner failure must produce 'failed', got {run.status}"
        )

        # Verify llm_planner tool call exists with failed status
        planner_call = next(
            (tc for tc in run.tool_calls if tc.name == "llm_planner"), None
        )
        assert planner_call is not None, "llm_planner tool call must exist"
        assert planner_call.status == "failed", (
            f"llm_planner must be failed, got {planner_call.status}"
        )

    @pytest.mark.anyio
    async def test_acceptance_no_analysis_evidence_fails_validation(
        self,
        monkeypatch,
        tmp_path,
        store,
        project,
        project_contexts,
        dataset_id,
        semantic_layer_fixture,
        config_dir,
        skills_dir,
    ):
        """Planner returning empty report without evidence must produce hard validation failures."""
        from app.agent.planner import Planner

        def mock_init(self, model_config):
            self.config = model_config
            self.index_content = ""

        async def mock_run_empty(*args, **kwargs):
            return {
                "report_md": "# No Data\n\nAnalysis produced no results.",
                "title": "Empty Analysis",
                "summary": "No data available",
                "selected_skills": ["product-analysis"],
                "candidate_angles": [],
                "caveats": ["No evidence produced"],
                "next_checks": [],
                "chart_specs": [],
            }

        monkeypatch.setattr(Planner, "__init__", mock_init)
        monkeypatch.setattr(Planner, "run_analysis", mock_run_empty)
        monkeypatch.setenv("TEST_API_KEY", "fake-key")

        workspace_dir = tmp_path / "workspace"
        workspace_dir.mkdir(exist_ok=True)
        orch = AgentOrchestrator(
            skills_dir=skills_dir, workspace_dir=workspace_dir,
            config_dir=config_dir, store=store,
            generated_code_execution="local",
        )
        request = AnalysisRequest(
            question="What is the monthly revenue trend?",
            project_id=project,
            dataset_ids=[dataset_id],
        )
        run = await orch.run(request)

        # Check validation results for evidence_coverage failure (now at top-level)
        validation_results = [
            v.model_dump(mode="json") for v in run.validation_results
        ]

        evidence_coverage = next(
            (v for v in validation_results if v.get("gate_id") == "evidence_coverage"), None
        )
        assert evidence_coverage is not None, "evidence_coverage gate must exist"
        assert not evidence_coverage.get("passed"), (
            "evidence_coverage must fail when no analysis evidence produced"
        )

        # Check for hard fail gates (severity="fail", passed=false)
        hard_fails = [
            v for v in validation_results
            if not v.get("passed") and v.get("severity") == "fail"
        ]
        assert len(hard_fails) > 0, (
            "Must have at least one hard validation failure when no evidence produced"
        )
        assert run.status == "failed", (
            f"Hard validation failures must produce 'failed' status, got {run.status}"
        )

    @pytest.mark.anyio
    async def test_acceptance_warning_only_produces_completed_with_warnings(
        self,
        monkeypatch,
        tmp_path,
        store,
        project,
        project_contexts,
        dataset_id,
        semantic_layer_fixture,
        config_dir,
        skills_dir,
    ):
        """Completed_with_warnings with only warning gates (no hard failures) is acceptable."""
        from app.agent.planner import Planner

        mock_init, mock_run = _make_mock_planner()
        monkeypatch.setattr(Planner, "__init__", mock_init)
        monkeypatch.setattr(Planner, "run_analysis", mock_run)
        monkeypatch.setenv("TEST_API_KEY", "fake-key")

        workspace_dir = tmp_path / "workspace"
        workspace_dir.mkdir(exist_ok=True)
        orch = AgentOrchestrator(
            skills_dir=skills_dir, workspace_dir=workspace_dir,
            config_dir=config_dir, store=store,
            generated_code_execution="local",
        )
        request = AnalysisRequest(
            question="What is the monthly revenue trend?",
            project_id=project,
            dataset_ids=[dataset_id],
        )
        run = await orch.run(request)

        # Must be completed or completed_with_warnings
        assert run.status in ("completed", "completed_with_warnings"), (
            f"Warning-only run must not be failed, got {run.status}"
        )

        # Check no hard failures
        run_log = next(
            (a for a in run.artifacts if a.type == ArtifactType.run_log and a.data and "validation_results" in a.data),
            None,
        )
        assert run_log is not None, "run_log with validation_results must exist"
        validation_results = run_log.data["validation_results"]
        hard_fails = [
            v for v in validation_results
            if not v.get("passed") and v.get("severity") == "fail"
        ]
        assert len(hard_fails) == 0, (
            f"Warning-only run must not have hard failures: {hard_fails}"
        )

    @pytest.mark.anyio
    async def test_acceptance_real_evidence_produces_charts_and_tables(
        self,
        monkeypatch,
        tmp_path,
        store,
        project,
        project_contexts,
        dataset_id,
        semantic_layer_fixture,
        config_dir,
        skills_dir,
    ):
        """Golden path must produce manifest with charts/tables and passing evidence gates."""
        from app.agent.planner import Planner

        mock_init, mock_run = _make_mock_planner()
        monkeypatch.setattr(Planner, "__init__", mock_init)
        monkeypatch.setattr(Planner, "run_analysis", mock_run)
        monkeypatch.setenv("TEST_API_KEY", "fake-key")

        workspace_dir = tmp_path / "workspace"
        workspace_dir.mkdir(exist_ok=True)
        orch = AgentOrchestrator(
            skills_dir=skills_dir, workspace_dir=workspace_dir,
            config_dir=config_dir, store=store,
            generated_code_execution="local",
        )
        request = AnalysisRequest(
            question="What is the monthly revenue trend?",
            project_id=project,
            dataset_ids=[dataset_id],
        )
        run = await orch.run(request)

        # Manifest must have charts or tables from executed analysis
        manifest_art = next(
            (a for a in run.artifacts if a.type == ArtifactType.visual_report), None
        )
        assert manifest_art is not None, "visual_report artifact must exist"
        data = manifest_art.data or {}
        manifest = data.get("manifest", {})
        charts = manifest.get("charts", [])
        tables = manifest.get("tables", [])
        assert len(charts) > 0 or len(tables) > 0, (
            f"Manifest must have charts or tables, got charts={len(charts)} tables={len(tables)}"
        )

        # Snapshot evidence_map must have at least one entry
        snapshot = data.get("snapshot", {})
        evidence_map = snapshot.get("evidence_map", {})
        assert len(evidence_map) > 0, (
            f"evidence_map must have entries, got {len(evidence_map)}"
        )

        # Evidence gates must pass
        run_log = next(
            (a for a in run.artifacts if a.type == ArtifactType.run_log and a.data and "validation_results" in a.data),
            None,
        )
        assert run_log is not None, "run_log with validation_results must exist"
        validation_results = run_log.data["validation_results"]
        ev_coverage = next(
            (v for v in validation_results if v.get("gate_id") == "evidence_coverage"), None
        )
        if ev_coverage:
            assert ev_coverage.get("passed"), "evidence_coverage must pass"
        ev_refs = next(
            (v for v in validation_results if v.get("gate_id") == "evidence_references"), None
        )
        if ev_refs:
            assert ev_refs.get("passed"), "evidence_references must pass"


class TestPlanOnlyBehavior:
    """Verify plan_only mode is safe and does not trigger evidence hard_failures."""

    def test_plan_only_with_profiles_does_not_trigger_hard_failure(self):
        """feedback with effective_data_backed=False should not hard-fail."""
        from app.agent.feedback import evaluate_attempt_feedback

        result = evaluate_attempt_feedback(
            question="What is revenue trend?",
            report_md="# Analysis\n\nRevenue grew by 12%.",
            execution_results=[],
            data_backed=False,
        )
        assert not result.get("should_retry"), (
            f"plan_only (data_backed=False) should not retry: {result}"
        )
        assert result.get("hard_failure_count", 0) == 0, (
            f"plan_only should have zero hard failures: {result}"
        )

    def test_plan_only_stub_result_not_seen_as_failure(self):
        """Stub returncode=0, status=skipped should not be failed evidence."""
        from app.agent.planner import Planner

        stub_result = {"returncode": 0, "status": "skipped", "tables": [], "charts": []}
        normalized = Planner._normalize_execution_result({}, stub_result)
        assert normalized["returncode"] == 0
        assert normalized["status"] == "skipped"
        assert normalized["tables"] == []
        assert Planner._has_successful_evidence([normalized]) is False, (
            "Stub with empty tables/charts should not count as successful evidence"
        )

    def test_plan_only_validation_skips_evidence_gates_safely(self):
        """run_and_apply_validation should skip gates without FrozenInstanceError."""
        from dataclasses import replace
        from app.agent.run_validation import _skip_evidence_gates_for_plan_only
        from app.tools.validation_types import ValidationResult

        results = [
            ValidationResult(gate_id="evidence_coverage", passed=False, severity="fail", message="No evidence"),
            ValidationResult(gate_id="visual_evidence_links", passed=False, severity="fail", message="Missing links"),
            ValidationResult(gate_id="markdown_content_preservation", passed=True, severity="pass", message="OK"),
        ]
        skipped = _skip_evidence_gates_for_plan_only(results)

        assert len(skipped) == 3
        for v in skipped:
            assert v.gate_id in {"evidence_coverage", "visual_evidence_links", "markdown_content_preservation"}
            if v.gate_id in ("evidence_coverage", "visual_evidence_links"):
                assert v.passed is True
                assert v.severity == "pass"
                assert "plan_only" in v.message
        assert skipped[2].passed is True  # non-evidence gate unchanged
