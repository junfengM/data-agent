import pytest

from app.agent.templates import TemplateRegistry
from app.agent.skills import SkillRegistry


@pytest.fixture
def skills_dir(tmp_path):
    """Create a temporary skills directory with test skills."""
    skills = {
        "product-analysis.md": "Name: Product Analysis\nUse When: General analysis\n\nLoad `$user-context` and `$chart-rules`.",
        "metric-diagnostics.md": "Name: Metric Diagnostics\nUse When: Why metrics changed\n\n",
        "kpi-reporting.md": "Name: KPI Reporting\nUse When: Weekly/monthly reports\n\n",
        "visualize-data.md": "Name: Visualize Data\nUse When: Charts and plots\n\n",
        "build-dashboard.md": "Name: Build Dashboard\nUse When: Dashboards\n\n",
        "build-report.md": "Name: Build Report\nUse When: Reports\n\n",
        "chart-rules.md": "Name: Chart Rules\nUse When: Chart selection rules\n\n",
    }
    for name, content in skills.items():
        (tmp_path / name).write_text(content)
    return tmp_path


@pytest.fixture
def registry(skills_dir):
    return SkillRegistry(skills_dir)


def test_list_skills(registry):
    skills = registry.list_skills()
    assert len(skills) == 7
    assert all(s.id for s in skills)
    assert all(s.name for s in skills)


def test_load_skill_content_product_analysis(registry):
    content = registry.load_skill_content("product-analysis")
    assert content is not None
    assert "Product Analysis" in content


def test_load_skill_content_chart_rules(registry):
    content = registry.load_skill_content("chart-rules")
    assert content is not None
    assert "Chart Rules" in content


def test_load_skill_content_nonexistent(registry):
    content = registry.load_skill_content("nonexistent")
    assert content is None


def test_load_skill_content_rejects_path_traversal(registry):
    for malicious in ("..", "../README", "../../etc/passwd", "/etc/passwd", "..%2Fsecret"):
        assert registry.load_skill_content(malicious) is None, malicious


def test_load_skill_content_rejects_symlink_escape(registry, tmp_path):
    outside = tmp_path.parent / "outside.md"
    outside.write_text("secret content", encoding="utf-8")
    link = registry.skills_dir / "linked.md"
    link.symlink_to(outside)
    assert registry.load_skill_content("linked") is None


def test_template_registry_rejects_path_traversal(tmp_path):
    templates_dir = tmp_path / "templates"
    templates_dir.mkdir()
    (templates_dir / "executive-summary.md").write_text("hello", encoding="utf-8")
    registry = TemplateRegistry(templates_dir)

    assert registry.template_for_intent("..") is None
    assert registry.template_for_intent("../../secret") is None
    assert registry.template_for_skill("..") is None
    assert registry.template_for_skill("../../etc/passwd") is None
    assert registry.template_for_intent("executive-summary") == "hello"


def test_skill_files_have_front_matter(registry):
    skills = registry.list_skills()
    for skill in skills:
        assert skill.name, f"Skill {skill.id} missing Name"
        # trigger comes from "Use When" front matter, may be empty
        assert hasattr(skill, "trigger"), f"Skill {skill.id} missing trigger attribute"


def test_parse_skill_refs(registry):
    content = registry.load_skill_content("product-analysis")
    assert content is not None
    refs = registry._parse_skill_refs(content)
    assert "chart-rules" in refs
    assert "user-context" not in refs


# ── Deterministic routing tests (SkillRouter) ──────────────────────────

from app.agent.skills import SkillRouter

METRIC_DIAG_QUESTIONS = [
    "为什么销售额下降了？",
    "为什么用户活跃度在降低？",
    "客单价上升的原因是什么？",
    "why did revenue drop last quarter?",
    "what caused the conversion rate decline?",
    "分析下毛利率下降的驱动因素",
    "帮我归因下复购率为什么降低了",
    "帮我做下细分下钻分析",
]

KPI_REPORT_QUESTIONS = [
    "生成本周销售周报",
    "请出具上月运营月报",
    "WBR需要更新了",
    "帮我准备Q2 QBR材料",
    "目标达成情况怎么样？",
    "帮我复盘下这个月的指标",
]

PRODUCT_ANALYSIS_QUESTIONS = [
    "帮我分析下最近产品销售趋势",
    "有什么可以优化的业务建议？",
    "帮我做下业务决策分析",
    "product recommendation for next quarter",
]

EXPLORE_DATA_QUESTIONS = [
    "分析一下数据有什么发现",
    "这份明细数据自由洞察一下",
    "看看有什么规律",
    "帮我做数据探索",
    "find insights from this transaction data",
    "what stands out in this spreadsheet",
    "做一下探索性分析",
]

BUILD_REPORT_QUESTIONS = [
    "生成分析报告",
    "帮我写一份报告",
    "输出一份完整的数据分析报告",
]

BUILD_DASHBOARD_QUESTIONS = [
    "创建一个销售仪表盘",
    "帮我搭个数据看板",
    "build a dashboard for monthly KPIs",
]

VISUALIZE_QUESTIONS = [
    "画个趋势图",
    "帮我可视化这些数据",
    "plot monthly revenue as bar chart",
]

MARKET_SIZING_QUESTIONS = [
    "估算下这个市场的规模",
    "做一下TAM分析",
    "market sizing for this product category",
]

DATA_QUALITY_QUESTIONS = [
    "检查下数据质量",
    "有没有缺失值？",
    "这个数据源健康吗？",
]


class TestSkillRouter:
    @pytest.mark.parametrize("question", METRIC_DIAG_QUESTIONS)
    def test_routes_to_metric_diagnostics(self, question):
        assert SkillRouter.route(question) == "metric-diagnostics"

    @pytest.mark.parametrize("question", KPI_REPORT_QUESTIONS)
    def test_routes_to_kpi_reporting(self, question):
        assert SkillRouter.route(question) == "kpi-reporting"

    @pytest.mark.parametrize("question", PRODUCT_ANALYSIS_QUESTIONS)
    def test_routes_to_product_analysis(self, question):
        assert SkillRouter.route(question) == "product-analysis"

    @pytest.mark.parametrize("question", EXPLORE_DATA_QUESTIONS)
    def test_routes_to_explore_data(self, question):
        assert SkillRouter.route(question) == "explore-data"

    @pytest.mark.parametrize("question", BUILD_REPORT_QUESTIONS)
    def test_routes_to_build_report(self, question):
        assert SkillRouter.route(question) == "build-report"

    @pytest.mark.parametrize("question", BUILD_DASHBOARD_QUESTIONS)
    def test_routes_to_build_dashboard(self, question):
        assert SkillRouter.route(question) == "build-dashboard"

    @pytest.mark.parametrize("question", VISUALIZE_QUESTIONS)
    def test_routes_to_visualize_data(self, question):
        assert SkillRouter.route(question) == "visualize-data"

    @pytest.mark.parametrize("question", MARKET_SIZING_QUESTIONS)
    def test_routes_to_market_sizing(self, question):
        assert SkillRouter.route(question) == "market-sizing"

    @pytest.mark.parametrize("question", DATA_QUALITY_QUESTIONS)
    def test_routes_to_analyze_data_quality(self, question):
        assert SkillRouter.route(question) == "analyze-data-quality"

    def test_unknown_question_defaults_to_product_analysis(self):
        assert SkillRouter.route("hello world") == "product-analysis"
        assert SkillRouter.route("随机文字") == "product-analysis"

    def test_route_with_reason_returns_matched_pattern(self):
        skill_id, pattern = SkillRouter.route_with_reason("为什么收入下降了")
        assert skill_id == "metric-diagnostics"
        assert "下降" in pattern

    def test_route_with_reason_default(self):
        skill_id, pattern = SkillRouter.route_with_reason("random query")
        assert skill_id == "product-analysis"
        assert pattern == "default"


# ── Skill availability tests ───────────────────────────────────────────

@pytest.fixture
def all_skills_dir(tmp_path):
    skills = {
        "product-analysis.md": "Name: Product Analysis\nUse When: General analysis\n\n",
        "metric-diagnostics.md": "Name: Metric Diagnostics\nUse When: Why metrics changed\n\n",
        "kpi-reporting.md": "Name: KPI Reporting\nUse When: Weekly/monthly reports\n\n",
        "visualize-data.md": "Name: Visualize Data\nUse When: Charts and plots\n\n",
        "build-dashboard.md": "Name: Build Dashboard\nUse When: Dashboards\n\n",
        "build-report.md": "Name: Build Report\nUse When: Reports\n\n",
        "chart-rules.md": "Name: Chart Rules\nUse When: Chart selection rules\n\n",
        "validate-data.md": "Name: Validate Data\nUse When: Pre-delivery QA\n\n",
        "analyze-data-quality.md": "Name: Analyze Data Quality\nUse When: Source trust assessment\n\n",
        "gather-business-context.md": "Name: Gather Business Context\nUse When: Missing context\n\n",
        "design-kpis.md": "Name: Design KPIs\nUse When: KPI framework design\n\n",
        "market-sizing.md": "Name: Market Sizing\nUse When: TAM/SAM/SOM\n\n",
        "jupyter-notebooks.md": "Name: Jupyter Notebooks\nUse When: Reproducible notebooks\n\n",
        "explore-data.md": "Name: Free Insight Discovery\nUse When: Open-ended data exploration\n\n",
        "user-context.md": "Name: User Context\nUse When: Load user context\n\n",
    }
    for name, content in skills.items():
        (tmp_path / name).write_text(content)
    return tmp_path


def test_all_primary_skills_available(all_skills_dir):
    registry = SkillRegistry(skills_dir=all_skills_dir)
    skill_ids = {s.id for s in registry.list_skills()}
    required = {"product-analysis", "metric-diagnostics", "kpi-reporting",
                 "visualize-data", "build-report", "build-dashboard",
                 "validate-data", "analyze-data-quality", "gather-business-context",
                 "design-kpis", "market-sizing", "jupyter-notebooks", "chart-rules",
                 "explore-data"}
    missing = required - skill_ids
    assert not missing, f"Missing skills: {missing}"


def test_user_context_loaded_as_auxiliary(all_skills_dir):
    registry = SkillRegistry(skills_dir=all_skills_dir)
    skill_ids = {s.id for s in registry.list_skills()}
    assert "user-context" in skill_ids


def test_router_prompt_renders_without_format_errors():
    from app.agent.planner import ROUTER_SYSTEM_PROMPT, _CHART_TYPES_STR
    rendered = ROUTER_SYSTEM_PROMPT.replace(
        "{_CHART_TYPES_STR}", _CHART_TYPES_STR
    ).replace(
        "{index_content}", "test index content"
    )
    assert "test index content" in rendered
    assert "Available tools" in rendered


def test_planner_prompt_renders_without_format_errors():
    from app.agent.planner import _RESOLVED_PLANNER_PROMPT
    assert len(_RESOLVED_PLANNER_PROMPT) > 100
    assert "data analyst" in _RESOLVED_PLANNER_PROMPT.lower()
    assert "{_CHART_TYPES_STR}" not in _RESOLVED_PLANNER_PROMPT
