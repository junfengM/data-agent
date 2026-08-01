
import pytest

from app.tools.path_safety import PathSafetyError, resolve_project_yaml_path


def test_resolve_project_yaml_path_accepts_relative_yaml(tmp_path):
    resolved = resolve_project_yaml_path(
        workspace_dir=tmp_path,
        project_id="proj_1",
        requested_path="semantic-layer.yaml",
    )

    assert resolved == (tmp_path / "projects" / "proj_1" / "semantic-layer.yaml").resolve()


def test_resolve_project_yaml_path_rejects_parent_escape(tmp_path):
    with pytest.raises(PathSafetyError, match="inside the project workspace"):
        resolve_project_yaml_path(
            workspace_dir=tmp_path,
            project_id="proj_1",
            requested_path="../other/semantic-layer.yaml",
        )


def test_resolve_project_yaml_path_rejects_non_yaml_suffix(tmp_path):
    with pytest.raises(PathSafetyError, match="yaml"):
        resolve_project_yaml_path(
            workspace_dir=tmp_path,
            project_id="proj_1",
            requested_path="semantic-layer.json",
        )


def test_resolve_project_yaml_path_rejects_existing_symlink(tmp_path):
    project_dir = tmp_path / "projects" / "proj_1"
    project_dir.mkdir(parents=True)
    target = tmp_path / "outside.yaml"
    target.write_text("metrics: []\n", encoding="utf-8")
    link = project_dir / "semantic-layer.yaml"
    link.symlink_to(target)

    with pytest.raises(PathSafetyError, match="symlink"):
        resolve_project_yaml_path(
            workspace_dir=tmp_path,
            project_id="proj_1",
            requested_path="semantic-layer.yaml",
        )


def test_resolve_project_yaml_path_accepts_absolute_path_inside_project(tmp_path):
    requested = tmp_path / "projects" / "proj_1" / "layers" / "active.yml"

    resolved = resolve_project_yaml_path(
        workspace_dir=tmp_path,
        project_id="proj_1",
        requested_path=str(requested),
    )

    assert resolved == requested.resolve(strict=False)


def test_rejects_legacy_external_absolute_path(tmp_path):
    external = tmp_path / "legacy" / "old-layer.yaml"
    external.parent.mkdir(parents=True)
    external.write_text("metrics: []\n", encoding="utf-8")

    with pytest.raises(PathSafetyError, match="inside the project workspace"):
        resolve_project_yaml_path(
            workspace_dir=tmp_path,
            project_id="proj_1",
            requested_path=str(external),
        )


def test_accepts_project_scoped_relative_path_even_when_file_missing(tmp_path):
    resolved = resolve_project_yaml_path(
        workspace_dir=tmp_path,
        project_id="proj_1",
        requested_path="custom-layer.yaml",
    )
    expected = (tmp_path / "projects" / "proj_1" / "custom-layer.yaml").resolve()
    assert resolved == expected
