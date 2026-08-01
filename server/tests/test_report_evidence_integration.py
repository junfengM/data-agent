"""Tests for report evidence integration gate in evaluate_attempt_feedback."""
from __future__ import annotations

from app.agent.feedback import evaluate_attempt_feedback


class TestReportEvidenceIntegration:
    def test_feedback_fails_when_file_chart_not_integrated_into_report_md(self):
        result = evaluate_attempt_feedback(
            question="请生成销售分析报告",
            report_md="# 报告\n\n收入增长明显，产品A贡献最大。",
            execution_results=[
                {
                    "name": "build_charts",
                    "returncode": 0,
                    "tables": [],
                    "charts": [
                        {
                            "name": "revenue_trend_by_product",
                            "title": "各产品月度收入趋势",
                            "path": "revenue_trend_by_product.html",
                            "asset_name": "revenue_trend_by_product.html",
                        }
                    ],
                }
            ],
            chart_specs=[
                {
                    "name": "revenue_trend_by_product",
                    "title": "各产品月度收入趋势",
                    "chart_type": "line",
                }
            ],
            data_backed=True,
            analysis_intent={"expected_output": "report"},
        )
        assert result["should_retry"] is True
        assert result["hard_failure_count"] >= 1
        assert any(
            item["source"] == "report_evidence_integration"
            for item in result["items"]
        )

    def test_feedback_passes_when_file_chart_link_is_integrated(self):
        result = evaluate_attempt_feedback(
            question="请生成销售分析报告",
            report_md=(
                "# 报告\n\n"
                "产品A是主要增长来源。\n\n"
                "[各产品月度收入趋势](revenue_trend_by_product.html)\n"
                "该图显示产品A在Q1持续增长。"
            ),
            execution_results=[
                {
                    "name": "build_charts",
                    "returncode": 0,
                    "tables": [],
                    "charts": [
                        {
                            "name": "revenue_trend_by_product",
                            "title": "各产品月度收入趋势",
                            "path": "revenue_trend_by_product.html",
                            "asset_name": "revenue_trend_by_product.html",
                        }
                    ],
                }
            ],
            chart_specs=[
                {
                    "name": "revenue_trend_by_product",
                    "title": "各产品月度收入趋势",
                    "chart_type": "line",
                }
            ],
            data_backed=True,
            analysis_intent={"expected_output": "report"},
        )
        assert not any(
            item["source"] == "report_evidence_integration"
            for item in result["items"]
        )

    def test_feedback_fails_when_table_not_integrated_into_report_md(self):
        result = evaluate_attempt_feedback(
            question="请生成销售分析报告",
            report_md="# 报告\n\n整体表现良好。",
            execution_results=[
                {
                    "name": "build_tables",
                    "returncode": 0,
                    "charts": [],
                    "tables": [
                        {
                            "name": "product_summary",
                            "columns": ["product", "total_revenue", "total_orders"],
                            "rows": [
                                {
                                    "product": "Product A",
                                    "total_revenue": 403000,
                                    "total_orders": 155,
                                }
                            ],
                        }
                    ],
                }
            ],
            chart_specs=[],
            data_backed=True,
            analysis_intent={"expected_output": "report"},
        )
        assert result["should_retry"] is True
        assert any(
            item["source"] == "report_evidence_integration"
            for item in result["items"]
        )

    def test_feedback_passes_when_table_values_are_rendered_in_report_md(self):
        result = evaluate_attempt_feedback(
            question="请生成销售分析报告",
            report_md=(
                "# 报告\n\n"
                "| product | total_revenue | total_orders |\n"
                "|---|---:|---:|\n"
                "| Product A | 403000 | 155 |\n"
            ),
            execution_results=[
                {
                    "name": "build_tables",
                    "returncode": 0,
                    "charts": [],
                    "tables": [
                        {
                            "name": "product_summary",
                            "columns": ["product", "total_revenue", "total_orders"],
                            "rows": [
                                {
                                    "product": "Product A",
                                    "total_revenue": 403000,
                                    "total_orders": 155,
                                }
                            ],
                        }
                    ],
                }
            ],
            chart_specs=[],
            data_backed=True,
            analysis_intent={"expected_output": "report"},
        )
        assert not any(
            item["source"] == "report_evidence_integration"
            for item in result["items"]
        )

    def test_feedback_retries_when_plotly_charts_generated_but_absent_from_report_md(self):
        chart_names = [
            "aov_trend_by_product",
            "mom_growth_comparison",
            "monthly_revenue_stacked",
            "orders_trend_by_product",
            "revenue_driver_waterfall",
            "revenue_share_pie",
            "revenue_trend_by_product",
        ]
        charts = [
            {
                "name": name,
                "title": name,
                "path": f"{name}.html",
                "asset_name": f"{name}.html",
            }
            for name in chart_names
        ]
        result = evaluate_attempt_feedback(
            question="请分析数据并生成报告",
            report_md="# 分析报告\n\n收入增长16.3%，订单增长14%。\n\n## 渠道分析\n\n线上渠道贡献最大。",
            execution_results=[
                {
                    "name": "driver_decomposition_and_charts",
                    "returncode": 0,
                    "tables": [],
                    "charts": charts,
                }
            ],
            chart_specs=[
                {"name": name, "title": name, "chart_type": "line"}
                for name in chart_names
            ],
            data_backed=True,
            analysis_intent={"expected_output": "report"},
        )
        assert result["should_retry"] is True
        assert any(
            item["source"] == "report_evidence_integration"
            for item in result["items"]
        )

    def test_feedback_passes_when_no_evidence_generated(self):
        result = evaluate_attempt_feedback(
            question="请生成报告",
            report_md="# 报告\n\n没有数据。",
            execution_results=[
                {"name": "noop", "returncode": 0, "tables": [], "charts": []}
            ],
            chart_specs=[],
            data_backed=True,
            analysis_intent={"expected_output": "report"},
        )
        assert not any(
            item["source"] == "report_evidence_integration"
            for item in result["items"]
        )
