from app.agent.orchestrator import AgentOrchestrator
from app.core.settings import Settings


def test_quarto_style_default_is_rich_business_report():
    settings = Settings()
    assert settings.quarto_style == "rich_business_report"


def test_orchestrator_from_settings_resolves_default_skills_dir(tmp_path):
    project_root = tmp_path / "agent"
    (project_root / "skills").mkdir(parents=True)

    settings = Settings(
        project_root=project_root,
        workspace_dir=project_root / "workspace",
        sqlite_path=project_root / "workspace" / "test.sqlite",
        generated_code_execution="disabled",
    )

    orchestrator = AgentOrchestrator.from_settings(settings)

    assert orchestrator.skill_registry.skills_dir == project_root / "skills"
