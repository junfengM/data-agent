import pytest

from app.agent.artifact_manifest_blocks import build_report_blocks
from app.models.schemas import ColumnProfile, DatasetProfile, ProjectContext, ReportBlockType


@pytest.fixture
def sample_profiles():
    return [
        DatasetProfile(
            dataset_id="ds1",
            filename="sales.csv",
            row_count=1000,
            column_count=5,
            columns=[
                ColumnProfile(name="date", dtype="object", non_null_count=1000, null_count=0, null_pct=0.0, unique_count=365),
                ColumnProfile(name="revenue", dtype="float64", non_null_count=990, null_count=10, null_pct=0.01, unique_count=500),
            ],
        )
    ]


@pytest.fixture
def sample_project_contexts():
    return [
        ProjectContext(
            id="ctx1",
            project_id="proj1",
            kind="business_context",
            title="Business Background",
            body="E-commerce platform focusing on electronics",
        ),
        ProjectContext(
            id="ctx2",
            project_id="proj1",
            kind="metric_definition",
            title="Revenue Definition",
            body="Revenue = price * quantity after discounts",
        ),
    ]


def test_build_report_blocks_basic():
    report_md = "## Summary\n\nTotal revenue increased by 15%.\n\n## Details\n\nQ1 was strong."
    blocks = build_report_blocks(
        title="Test Report",
        report_md=report_md,
        step_results=[],
        plan_caveats=[],
        profiles=[],
        project_contexts=None,
    )

    assert len(blocks) >= 3
    assert blocks[0].type == ReportBlockType.heading
    assert blocks[0].data["text"] == "Test Report"
    assert blocks[0].data["level"] == 1


def test_build_report_blocks_heading_levels():
    report_md = "## H2 Section\n\nContent.\n\n### H3 Subsection\n\nMore content.\n\n#### H4 Detail\n\nDetail here."
    blocks = build_report_blocks(
        title="Test",
        report_md=report_md,
        step_results=[],
        plan_caveats=[],
        profiles=[],
        project_contexts=None,
    )

    headings = [b for b in blocks if b.type == ReportBlockType.heading]
    assert len(headings) >= 4
    assert headings[1].data["level"] == 2
    assert headings[2].data["level"] == 3
    assert headings[3].data["level"] == 4


def test_build_report_blocks_embed_tables():
    report_md = "## Analysis\n\nSee the revenue table below."
    step_results = [
        {
            "tables": [
                {
                    "name": "revenue",
                    "columns": ["region", "total"],
                    "preview": [{"region": "East", "total": 100}],
                }
            ],
            "charts": [],
        }
    ]
    blocks = build_report_blocks(
        title="Test",
        report_md=report_md,
        step_results=step_results,
        plan_caveats=[],
        profiles=[],
        project_contexts=None,
    )

    table_blocks = [b for b in blocks if b.type == ReportBlockType.table]
    assert len(table_blocks) == 1
    assert table_blocks[0].data["title"] == "revenue"


def test_build_report_blocks_embed_charts():
    report_md = "## Visualization\n\nThe trend chart shows growth."
    step_results = [
        {
            "tables": [],
            "charts": [
                {
                    "name": "trend",
                    "type": "png",
                    "path": "/path/to/trend.png",
                }
            ],
        }
    ]
    blocks = build_report_blocks(
        title="Test",
        report_md=report_md,
        step_results=step_results,
        plan_caveats=[],
        profiles=[],
        project_contexts=None,
    )

    chart_blocks = [b for b in blocks if b.type == ReportBlockType.chart]
    assert len(chart_blocks) == 1
    assert chart_blocks[0].data["title"] == "trend"
    assert chart_blocks[0].data["render_mode"] == "file"


def test_build_report_blocks_caveats():
    blocks = build_report_blocks(
        title="Test",
        report_md="## Summary\n\nContent.",
        step_results=[],
        plan_caveats=["Data has gaps in Q3", "Sample size is small"],
        profiles=[],
        project_contexts=None,
    )

    callout_blocks = [b for b in blocks if b.type == ReportBlockType.callout]
    assert len(callout_blocks) == 2
    assert all(b.data["severity"] == "warning" for b in callout_blocks)


def test_build_report_blocks_source_notes(sample_profiles):
    blocks = build_report_blocks(
        title="Test",
        report_md="## Summary\n\nContent.",
        step_results=[],
        plan_caveats=[],
        profiles=sample_profiles,
        project_contexts=None,
    )

    source_blocks = [b for b in blocks if b.type == ReportBlockType.source_note]
    assert len(source_blocks) == 1
    assert "sales.csv" in source_blocks[0].data["text"]


def test_build_report_blocks_project_contexts(sample_project_contexts):
    blocks = build_report_blocks(
        title="Test",
        report_md="## Summary\n\nContent.",
        step_results=[],
        plan_caveats=[],
        profiles=[],
        project_contexts=sample_project_contexts,
    )

    info_callouts = [b for b in blocks if b.type == ReportBlockType.callout and b.data["severity"] == "info"]
    assert len(info_callouts) == 1
    assert "Business Context" in info_callouts[0].data["text"]
    assert "Metric Definition" in info_callouts[0].data["text"]
    assert "E-commerce platform" in info_callouts[0].data["text"]
