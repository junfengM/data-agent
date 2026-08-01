from __future__ import annotations

from app.agent.planner import (
    LLM_CONTEXT_HARD_CHARS,
    LLM_CONTEXT_WARN_CHARS,
    Planner,
)
from app.core.settings import get_settings

_settings = get_settings()
_CONTEXT_WARN = _settings.planner_context_warn_chars


def make_test_planner():
    import os
    os.environ.setdefault("DATA_AGENT_OPENAI_API_KEY", "test-key")
    from app.models.schemas import ModelConfigSummary
    config = ModelConfigSummary(
        id="test-model",
        provider="openai",
        model="test-model",
        api_key_env="DATA_AGENT_OPENAI_API_KEY",
        base_url="http://localhost",
        temperature=0.2,
        max_tokens=None,
    )
    return Planner(config)


class TestContextBudgetSnapshot:
    def test_counts_message_content(self):
        messages = [
            {"role": "system", "content": "abc"},
            {"role": "user", "content": "hello"},
        ]
        snapshot = Planner._context_budget_snapshot(messages, [])
        assert snapshot["message_content_chars"] == 8
        assert snapshot["tool_call_argument_chars"] == 0
        assert snapshot["estimated_context_chars"] == 8

    def test_counts_tool_call_arguments(self):
        messages = [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "tc1",
                        "type": "function",
                        "function": {
                            "name": "execute_code",
                            "arguments": "x" * 5000,
                        },
                    }
                ],
            }
        ]
        snapshot = Planner._context_budget_snapshot(messages, [])
        assert snapshot["message_content_chars"] == 0
        assert snapshot["tool_call_argument_chars"] == 5000
        assert snapshot["estimated_context_chars"] == 5000

    def test_counts_tool_result_chars(self):
        messages = [
            {"role": "tool", "content": "y" * 3000}
        ]
        snapshot = Planner._context_budget_snapshot(messages, [])
        assert snapshot["tool_result_chars"] == 3000
        assert snapshot["message_content_chars"] == 3000

    def test_counts_execution_evidence(self):
        execution_results = [
            {"tables": [{"name": "t1"}, {"name": "t2"}], "charts": [{"name": "c1"}]},
            {"tables": [], "charts": []},
        ]
        snapshot = Planner._context_budget_snapshot([], execution_results)
        assert snapshot["table_count"] == 2
        assert snapshot["chart_count"] == 1
        assert snapshot["execution_count"] == 2

    def test_largest_items_sorted_by_total_chars(self):
        messages = [
            {"role": "system", "content": "a" * 100},
            {"role": "user", "content": "b" * 200},
            {"role": "tool", "content": "c" * 50},
        ]
        snapshot = Planner._context_budget_snapshot(messages, [])
        items = snapshot["largest_context_items"]
        assert items[0]["total_chars"] == 200
        assert items[0]["role"] == "user"

    def test_budget_action_warn(self):
        msgs = [{"role": "system", "content": "x" * (_CONTEXT_WARN + 1)}]
        snapshot = Planner._context_budget_snapshot(msgs, [])
        assert snapshot["budget_action"] == "warn"

    def test_budget_action_continue_under_threshold(self):
        msgs = [{"role": "system", "content": "x" * (_CONTEXT_WARN - 1)}]
        snapshot = Planner._context_budget_snapshot(msgs, [])
        assert snapshot["budget_action"] == "continue"


class TestShouldDetachForContextBudget:
    def test_detach_with_evidence_over_threshold(self):
        budget = {"estimated_context_chars": _CONTEXT_WARN + 1}
        execution_results = [
            {
                "status": "completed",
                "returncode": 0,
                "tables": [{"name": "t"}],
                "charts": [],
            }
        ]
        assert Planner._should_detach_for_context_budget(
            budget, execution_results, detached_finalizer_active=False,
        )

    def test_no_detach_without_evidence(self):
        budget = {"estimated_context_chars": _CONTEXT_WARN + 1}
        assert not Planner._should_detach_for_context_budget(
            budget, [], detached_finalizer_active=False,
        )

    def test_no_detach_under_threshold(self):
        budget = {"estimated_context_chars": _CONTEXT_WARN - 1}
        execution_results = [
            {"status": "completed", "returncode": 0, "tables": [{"name": "t"}], "charts": []}
        ]
        assert not Planner._should_detach_for_context_budget(
            budget, execution_results, detached_finalizer_active=False,
        )

    def test_no_detach_already_active(self):
        budget = {"estimated_context_chars": _CONTEXT_WARN + 1}
        execution_results = [
            {"status": "completed", "returncode": 0, "tables": [{"name": "t"}], "charts": []}
        ]
        assert not Planner._should_detach_for_context_budget(
            budget, execution_results, detached_finalizer_active=True,
        )

    def test_no_detach_failed_steps_only(self):
        budget = {"estimated_context_chars": _CONTEXT_WARN + 1}
        execution_results = [
            {"status": "failed", "returncode": 1, "tables": [{"name": "partial", "partial": True}], "charts": []}
        ]
        assert not Planner._should_detach_for_context_budget(
            budget, execution_results, detached_finalizer_active=False,
        )


class TestContextBudgetWarning:
    def test_budget_action_high_context_returns_warn(self):
        msgs = [{"role": "system", "content": "x" * (_CONTEXT_WARN + 1)}]
        snapshot = Planner._context_budget_snapshot(msgs, [])
        assert snapshot["budget_action"] == "warn", (
            "High context should emit 'warn' action"
        )

    def test_full_context_budget_snapshot_has_all_fields(self):
        msgs = [
            {"role": "system", "content": "s" * 5000},
            {"role": "user", "content": "u" * 3000},
            {"role": "tool", "content": "t" * 10000},
        ]
        er = [
            {"tables": [{"name": "t1"}], "charts": [{"name": "c1"}]},
            {"tables": [], "charts": []},
        ]
        snapshot = Planner._context_budget_snapshot(msgs, er)
        assert "estimated_context_chars" in snapshot
        assert "budget_action" in snapshot
        assert snapshot["table_count"] == 1
        assert snapshot["chart_count"] == 1
        assert snapshot["execution_count"] == 2
        assert snapshot["warn_threshold"] == LLM_CONTEXT_WARN_CHARS
        assert snapshot["hard_threshold"] == LLM_CONTEXT_HARD_CHARS

    def test_hard_threshold_is_none_by_default(self):
        msgs = [{"role": "system", "content": "x" * 1000}]
        snapshot = Planner._context_budget_snapshot(msgs, [])
        assert snapshot["hard_threshold"] is None, (
            "hard_threshold should be None when planner_context_hard_chars is not set"
        )

    def test_full_context_snapshot_does_not_trigger_detach_action(self):
        msgs = [{"role": "system", "content": "x" * (_CONTEXT_WARN + 1)}]
        snapshot = Planner._context_budget_snapshot(msgs, [])
        assert snapshot["budget_action"] == "warn", (
            "High context should produce 'warn' action, not 'detach_finalizer'"
        )
        assert "detach_threshold" not in snapshot, (
            "detach_threshold should not be in snapshot (no detach concept anymore)"
        )


class TestPlannerBudgetsAndTracePrivacy:
    def test_available_tools_removes_execute_code_at_execution_budget(self, monkeypatch):
        settings = get_settings()
        monkeypatch.setattr(settings, "planner_max_code_executions", 1)
        planner = make_test_planner()

        names_at_zero = {t["function"]["name"] for t in planner._available_tools(0)}
        assert "execute_code" in names_at_zero

        names_at_limit = {t["function"]["name"] for t in planner._available_tools(1)}
        assert "execute_code" not in names_at_limit
        assert "save_semantic_finding" not in names_at_limit
        assert "load_skill" in names_at_limit

    def test_trace_prompt_snapshots_default_to_off(self):
        assert get_settings().trace_persist_prompt_snapshots is False
