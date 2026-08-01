from app.tools.validation import validate_renderability


class TestValidateRenderability:
    def test_all_standard_types_pass(self):
        artifacts = [
            {"type": "structured_report"},
            {"type": "markdown_report"},
            {"type": "html_report"},
            {"type": "table"},
            {"type": "chart"},
            {"type": "dashboard"},
            {"type": "run_log"},
        ]
        result = validate_renderability(artifacts)
        assert result.passed
        assert result.details["non_renderable"] == 0

    def test_visual_report_passes(self):
        artifacts = [{"type": "visual_report"}]
        result = validate_renderability(artifacts)
        assert result.passed
        assert result.details["non_renderable"] == 0

    def test_unknown_type_fails(self):
        artifacts = [{"type": "unknown_type"}]
        result = validate_renderability(artifacts)
        assert not result.passed
        assert result.details["non_renderable"] == 1

    def test_mixed_known_and_unknown_types(self):
        artifacts = [
            {"type": "visual_report"},
            {"type": "chart"},
            {"type": "unknown_type"},
        ]
        result = validate_renderability(artifacts)
        assert not result.passed
        assert result.details["non_renderable"] == 1

    def test_empty_artifacts_passes(self):
        result = validate_renderability([])
        assert result.passed
        assert result.details["non_renderable"] == 0
