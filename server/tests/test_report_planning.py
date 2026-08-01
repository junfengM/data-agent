from app.agent.artifact_manifest import build_artifact_manifest
from app.agent.report_planning import action_items_from_markdown, infer_report_intent
from app.models.schemas import ArtifactBlockType, ColumnProfile, DatasetProfile
from app.tools.validation import validate_report_quality


def _profile() -> DatasetProfile:
    return DatasetProfile(
        dataset_id="ds_1",
        filename="sales.csv",
        row_count=2,
        column_count=5,
        columns=[
            ColumnProfile(
                name="segment",
                dtype="object",
                non_null_count=2,
                null_count=0,
                null_pct=0,
                unique_count=2,
            ),
            ColumnProfile(
                name="revenue",
                dtype="int64",
                non_null_count=2,
                null_count=0,
                null_pct=0,
                unique_count=2,
                mean_value=90,
            ),
            ColumnProfile(
                name="growth",
                dtype="float64",
                non_null_count=2,
                null_count=0,
                null_pct=0,
                unique_count=2,
                mean_value=0.2,
            ),
            ColumnProfile(
                name="risk_score",
                dtype="float64",
                non_null_count=2,
                null_count=0,
                null_pct=0,
                unique_count=2,
                mean_value=0.4,
            ),
            ColumnProfile(
                name="month",
                dtype="object",
                non_null_count=2,
                null_count=0,
                null_pct=0,
                unique_count=2,
            ),
        ],
    )


def test_infer_report_intent_prefers_management_visual_reports():
    intent = infer_report_intent(
        "经营月报",
        "## 核心指标速览\n本报告面向管理层复盘业务表现。",
    )

    assert intent.audience == "executive"
    assert intent.format == "dashboard"
    assert intent.visual_density == "high"
    assert "executive_or_business_language" in intent.rationale


def test_action_items_from_markdown_extracts_structured_recommendations():
    items = action_items_from_markdown(
        "## 核心结论\n表现改善。\n\n"
        "## 建议行动\n"
        "- 高优先级：复盘增长渠道并扩大投入。负责人：增长团队。本周完成。\n"
        "- 低优先级：整理历史口径文档。\n"
    )

    assert [item["priority"] for item in items] == ["high", "low"]
    assert "增长渠道" in items[0]["text"]
    assert items[0]["owner_hint"] == "增长团队"
    assert items[0]["due_hint"] == "本周"


def test_build_artifact_manifest_adds_plan_claim_taxonomy_actions_and_visuals():
    report_md = (
        "# 经营月报\n\n"
        "## 核心结论\n"
        "kpi_summary 显示 revenue 达到 120，较上期增长，是核心业务变化。\n\n"
        "## 风险\n"
        "kpi_summary 的 risk_score 提示 A 渠道存在风险，需要重点关注。\n\n"
        "## 趋势与贡献\n"
        "kpi_summary 按 month 展示趋势，growth 和 contribution 用于拆解变化。\n\n"
        "## 建议行动\n"
        "- 高优先级：复盘 kpi_summary 中增长渠道并扩大投入。负责人：增长团队。本周完成。\n"
    )
    step_results = [
        {
            "name": "analysis",
            "tables": [
                {
                    "name": "kpi_summary",
                    "source": "sales.csv",
                    "columns": ["month", "segment", "revenue", "growth", "risk_score", "contribution"],
                    "preview": [
                        {"month": "2026-05", "segment": "A", "revenue": 120, "growth": 0.3, "risk_score": 0.8, "contribution": 30},
                        {"month": "2026-06", "segment": "B", "revenue": 60, "growth": -0.1, "risk_score": 0.2, "contribution": -10},
                    ],
                }
            ],
            "charts": [],
        }
    ]

    manifest, snapshot = build_artifact_manifest(
        title="经营月报",
        report_md=report_md,
        step_results=step_results,
        profiles=[_profile()],
        semantic_layer={
            "metrics": [
                {"name": "revenue", "source_column": "revenue", "aggregation": "sum"},
            ]
        },
    )

    assert manifest.report_intent is not None
    assert manifest.report_intent.audience == "executive"
    assert manifest.report_plan is not None
    assert [section.role for section in manifest.report_plan.sections][:2] == ["summary", "key_findings"]
    assert manifest.report_plan.evidence_budget["primary_blocks"] == 8

    assert manifest.claims
    assert manifest.claims[0].evidence_ids
    assert {claim.claim_type for claim in manifest.claims} & {"fact", "risk", "diagnosis"}
    assert any(claim.metric_refs for claim in manifest.claims)

    assert manifest.actions
    assert manifest.actions[0].priority == "high"
    assert manifest.actions[0].owner_hint == "增长团队"
    assert manifest.actions[0].supporting_claim_ids
    assert any(block.action_ids for block in manifest.blocks)
    assert any(block.claim_ids for block in manifest.blocks)
    assert any(block.section_role for block in manifest.blocks if block.claim_ids or block.action_ids)

    visual_types = {block.type for block in manifest.blocks}
    assert ArtifactBlockType.next_action_list in visual_types
    assert ArtifactBlockType.risk_panel in visual_types
    assert ArtifactBlockType.trend_panel in visual_types
    assert ArtifactBlockType.delta_bridge in visual_types

    assert any(block.evidence_priority == "primary" for block in manifest.blocks)
    assert any(entry.priority == "primary" for entry in snapshot.evidence_map)

    result = validate_report_quality([block.model_dump(mode="json") for block in manifest.blocks])
    assert result.passed is True
    assert result.severity in {"pass", "warning"}


def test_validate_report_quality_fails_appendix_claims():
    result = validate_report_quality([
        {
            "id": "block_1",
            "type": "markdown",
            "claim_ids": ["claim_1"],
            "evidence_ids": ["table_1"],
            "evidence_priority": "appendix",
            "section_role": "summary",
        }
    ])

    assert result.passed is False
    assert result.severity == "fail"
