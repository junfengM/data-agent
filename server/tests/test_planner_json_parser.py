from __future__ import annotations

from app.agent.planner import Planner


class TestExtractJsonEnhanced:
    def test_fenced_json_with_preamble(self):
        content = '下面是报告：\n```json\n{"title":"T","report_md":"# R"}\n```'
        payload = Planner._extract_json(content)
        assert payload is not None
        assert payload["report_md"] == "# R"

    def test_fenced_json_without_lang_label(self):
        content = '```\n{"title":"T","report_md":"# R"}\n```'
        payload = Planner._extract_json(content)
        assert payload is not None
        assert payload["title"] == "T"

    def test_raw_json_with_trailing_text(self):
        content = '{"title":"T","report_md":"# R"}\nDone.'
        payload = Planner._extract_json(content)
        assert payload is not None
        assert payload["title"] == "T"

    def test_json_with_preamble_no_fence(self):
        content = 'Here is the report:\n\n{"title":"Test","report_md":"# Analysis"}'
        payload = Planner._extract_json(content)
        assert payload is not None
        assert payload["title"] == "Test"

    def test_report_md_containing_braces(self):
        content = '{"title":"T","report_md":"| col | val |\\n|---|-----|\\n|{a}| 1 |"}'
        payload = Planner._extract_json(content)
        assert payload is not None
        assert payload["report_md"] is not None

    def test_multiple_json_candidates_first_valid(self):
        content = '{"a": 1}\n{"b": 2}'
        payload = Planner._extract_json(content)
        assert payload is not None
        assert payload == {"a": 1}

    def test_invalid_content_returns_none(self):
        assert Planner._extract_json("") is None
        assert Planner._extract_json("not json at all") is None
        assert Planner._extract_json("[1, 2, 3]") is None  # list, not dict

    def test_nested_braces_in_report_md(self):
        content = (
            '{"title":"T","report_md":"code: `{\\"key\\": \\"val\\"}`"}'
        )
        payload = Planner._extract_json(content)
        assert payload is not None
        assert payload["title"] == "T"

    def test_fenced_with_explanation_before_and_after(self):
        content = (
            "Now I will output the final report.\n\n"
            "```json\n"
            '{"title":"Analysis","report_md":"# Results\\n\\nKey findings.","summary":"good"}\n'
            "```\n\n"
            "That concludes the analysis."
        )
        payload = Planner._extract_json(content)
        assert payload is not None
        assert payload["title"] == "Analysis"
        assert payload.get("report_md")

    def test_force_finalize_markdown_fallback(self):
        payload = Planner._coerce_final_payload(
            "# Report\n\n## 结论\n\n销售增长明显。",
            question="Q",
            analysis_intent={},
            force_finalize=True,
        )
        assert payload is not None
        assert payload["report_md"].startswith("# Report")

    def test_force_finalize_false_returns_none_for_non_json(self):
        payload = Planner._coerce_final_payload(
            "Not valid JSON at all",
            question="Q",
            analysis_intent={},
            force_finalize=False,
        )
        assert payload is None

    def test_prefers_payload_with_report_md_over_schema_example(self):
        content = (
            '{"example": true}\n'
            '```json\n'
            '{"title":"T","report_md":"# R"}\n'
            '```'
        )
        payload = Planner._extract_json(content)
        assert payload is not None
        assert payload["report_md"] == "# R"

    def test_falls_back_to_first_dict_when_no_report_md(self):
        content = '{"a": 1}\n{"b": 2}'
        payload = Planner._extract_json(content)
        assert payload == {"a": 1}
