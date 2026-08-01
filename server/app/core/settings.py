from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    project_root: Path = Field(default_factory=lambda: Path(__file__).resolve().parents[3])
    config_dir: Path | None = None
    workspace_dir: Path | None = None
    skills_dir: Path | None = None
    sqlite_path: Path | None = None
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    generated_code_execution: str = "disabled"  # "disabled" | "local-dev" (or "local") | "sandbox"
    templates_dir: Path | None = None
    emit_debug_structured_report: bool = False  # emit legacy "Block Report (Debug)" artifact

    # Quarto runtime detection (Web Report renderer)
    quarto_bin: str | None = None  # explicit path to quarto binary
    quarto_version: str = "1.9.38"  # managed install target version
    quarto_auto_install: bool = False  # do NOT auto-install at startup
    quarto_style: str = "rich_business_report"  # "business" | "rich_business_report"
    quarto_render_timeout_seconds: int = 600

    # Planner / long-context settings
    planner_max_tool_iterations: int = 80
    planner_max_code_executions: int = 20
    planner_context_warn_chars: int = 300_000
    planner_context_hard_chars: int | None = None  # None = no hard limit; set to enable warning

    # Trace privacy: prompt snapshots are only persisted when explicitly enabled.
    trace_persist_prompt_snapshots: bool = False

    # Finalizer evidence bundle settings
    finalizer_length_retry_limit: int = 2
    finalizer_max_tables: int = 160
    finalizer_max_charts: int = 160
    finalizer_max_failed_steps: int = 20
    finalizer_stdout_chars_per_step: int = 5000
    finalizer_table_preview_rows: int = 20
    finalizer_table_preview_columns: int = 40
    finalizer_profile_columns: int = 300

    # LLM tool-result compaction
    llm_stdout_char_limit: int = 5000
    llm_stdout_max_lines: int = 120
    llm_stderr_char_limit: int = 3000
    llm_table_preview_rows: int = 20
    llm_table_preview_columns: int = 40
    llm_wide_table_column_threshold: int = 80
    llm_wide_table_column_sample: int = 40
    llm_failed_code_excerpt_limit: int = 5000

    # Analysis execution limits
    analysis_execution_timeout_seconds: int = 600
    analysis_max_output_files: int = 500
    analysis_max_output_bytes: int = 200 * 1024 * 1024

    model_config = SettingsConfigDict(env_prefix="DATA_AGENT_", env_file=".env", extra="ignore")

    @field_validator("config_dir", "workspace_dir", "skills_dir", "sqlite_path", "templates_dir",
                     mode="before")
    @classmethod
    def _empty_str_to_none(cls, v: Any) -> Any:
        """Treat empty string env vars as None so resolved_* properties fall back correctly."""
        if isinstance(v, str) and v.strip() == "":
            return None
        return v

    @property
    def resolved_config_dir(self) -> Path:
        return self.config_dir or self.project_root / "config"

    @property
    def resolved_workspace_dir(self) -> Path:
        return self.workspace_dir or self.project_root / "workspace"

    @property
    def resolved_skills_dir(self) -> Path:
        return self.skills_dir or self.project_root / "skills"

    @property
    def resolved_templates_dir(self) -> Path:
        return self.templates_dir or self.project_root / "templates"

    @property
    def resolved_sqlite_path(self) -> Path:
        return self.sqlite_path or self.resolved_workspace_dir / "data-agent.sqlite"


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.resolved_workspace_dir.mkdir(parents=True, exist_ok=True)
    return settings
