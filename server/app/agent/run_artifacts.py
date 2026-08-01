"""Report artifact writing helpers (extracted from orchestrator.py)."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from app.models.schemas import Artifact, ArtifactType
from app.tools.notebooks import write_profile_notebook
from app.tools.redaction import redact_local_paths
from app.tools.reports import write_html_report, write_markdown_report

logger = logging.getLogger(__name__)


def _safe_artifact_path(file_path: Path, workspace_root: Path | None = None) -> Path | None:
    if file_path is None:
        return None
    if workspace_root is not None:
        ws = str(workspace_root).rstrip("/")
        if str(file_path).startswith(ws):
            return Path(file_path.name)
    return Path(redact_local_paths(str(file_path)))


def write_markdown_artifact(
    artifacts_dir: Path,
    run_id: str,
    report_md: str,
    workspace_root: Path | None = None,
) -> tuple[str, Artifact]:
    report_path = write_markdown_report(
        artifacts_dir=artifacts_dir,
        run_id=run_id,
        title="Analysis Report",
        body=report_md,
    )
    artifact = Artifact(
        type=ArtifactType.markdown_report,
        title="Analysis Report",
        path=_safe_artifact_path(report_path, workspace_root),
        content=report_md,
    )
    return report_path, artifact


def write_visual_report_artifact(
    manifest: Any,
    snapshot: Any,
    report_md: str,
    workspace_root: Path | None = None,
) -> Artifact:
    manifest_data = manifest.model_dump(mode="json")
    snapshot_data = snapshot.model_dump(mode="json")
    data = {
        "manifest": manifest_data,
        "snapshot": snapshot_data,
        "validation_results": [],
        "validation_passed": False,
        "surface": "visual_report",
        "artifact_role": "primary_report",
    }
    return Artifact(
        type=ArtifactType.visual_report,
        title="图文分析报告",
        content=report_md,
        data=redact_local_paths(data, workspace_root=workspace_root),
    )


def write_html_artifact(
    artifacts_dir: Path,
    run_id: str,
    report_md: str,
    workspace_root: Path | None = None,
) -> tuple[str, Artifact]:
    html_path = write_html_report(
        artifacts_dir=artifacts_dir,
        run_id=run_id,
        title="Analysis Report",
        markdown_body=report_md,
    )
    artifact = Artifact(
        type=ArtifactType.html_report,
        title="HTML Report",
        path=_safe_artifact_path(html_path, workspace_root),
    )
    return html_path, artifact


def write_web_report_artifact(
    *,
    run_id: str,
    report_md: str,
    manifest: dict[str, Any] | None = None,
    snapshot: dict[str, Any] | None = None,
    project_name: str | None = None,
    artifacts_dir: Path | None = None,
    workspace_root: Path | None = None,
) -> Artifact | None:
    """Generate the polished Web Report HTML artifact via Quarto only.

    The previous experimental `delivery_renderer_v2` fallback has been retired.
    If Quarto is unavailable or rendering fails, no Web Report artifact is emitted;
    the main analysis run remains successful because Web Report generation is an
    optional downstream delivery surface.

    `manifest` and `snapshot` are accepted for backwards-compatible call sites but
    are intentionally unused by the Quarto renderer.
    """
    del manifest, snapshot

    try:
        from app.agent.quarto_renderer import render_quarto_report

        result = render_quarto_report(
            report_md=report_md,
            run_id=run_id,
            project_name=project_name,
            artifacts_dir=artifacts_dir,
        )
    except Exception:
        logger.warning("quarto_web_report_render_failed", exc_info=True)
        return None

    if result is None:
        logger.info("quarto_web_report_not_generated")
        return None

    html, metadata = result
    metadata = {
        **metadata,
        "renderer": "quarto_html",
        "fallback_used": False,
        "fallback_renderer": None,
    }

    run_dir = artifacts_dir or Path(".")
    web_path = run_dir / "web_report.html"
    web_path.parent.mkdir(parents=True, exist_ok=True)
    web_path.write_text(html, encoding="utf-8")

    return Artifact(
        id=f"{run_id}:web_report",
        type=ArtifactType.html_report,
        title="网页版报告",
        path=_safe_artifact_path(web_path, workspace_root),
        content=html[:2000],
        data=redact_local_paths(metadata, workspace_root=workspace_root),
    )


def write_notebook_artifact(
    artifacts_dir: Path,
    run_id: str,
    question: str,
    dataset_paths: list[Path],
    profiles: list[Any],
    workspace_root: Path | None = None,
) -> tuple[str, Artifact]:
    notebook_path = write_profile_notebook(
        artifacts_dir=artifacts_dir,
        run_id=run_id,
        title="Analysis Notebook",
        question=question,
        dataset_paths=dataset_paths,
        profiles=profiles,
    )
    artifact = Artifact(
        type=ArtifactType.notebook,
        title="Analysis Notebook",
        path=_safe_artifact_path(notebook_path, workspace_root),
    )
    return notebook_path, artifact


def build_web_report_package(
    run_id: str,
    artifacts_dir: Path,
    output_path: Path,
) -> Path:
    import re
    import shutil
    import zipfile
    from urllib.parse import unquote

    web_report_path = artifacts_dir / "web_report.html"
    if not web_report_path.is_file():
        raise FileNotFoundError(f"web_report.html not found at {web_report_path}")

    html = web_report_path.read_text(encoding="utf-8")

    # iframe src: /api/runs/{run_id}/assets/{name}.html or local filenames
    asset_pattern = re.compile(
        r'src=["\'](?:/api/runs/[^/]+/assets/)?([^"\']+\.html)["\']'
    )
    chart_files: set[str] = set()
    for m in asset_pattern.finditer(html):
        name = Path(unquote(m.group(1))).name
        if Path(name).suffix.lower() == ".html":
            chart_files.add(name)

    pkg_dir = output_path.parent / f"web_report_pkg_{run_id}"
    pkg_dir.mkdir(parents=True, exist_ok=True)
    assets_dir = pkg_dir / "assets"
    assets_dir.mkdir(exist_ok=True)

    copied: dict[str, str] = {}
    missing: list[str] = []
    for chart_name in sorted(chart_files):
        src = artifacts_dir / chart_name
        if src.is_file():
            dst = assets_dir / chart_name
            shutil.copy2(src, dst)
            copied[chart_name] = f"assets/{chart_name}"
        else:
            missing.append(chart_name)

    if missing:
        raise FileNotFoundError(
            "Web report package is missing chart asset(s): " + ", ".join(missing)
        )

    for chart_name, asset_path in copied.items():
        html = re.sub(
            rf'src=["\'](?:/api/runs/[^/]+/assets/)?{re.escape(chart_name)}["\']',
            f'src="{asset_path}"',
            html,
        )

    html = re.sub(
        r'src=["\']/api/runs/[^/]+/assets/',
        'src="assets/',
        html,
    )

    html = re.sub(
        r'(src|href)=["\'](?:https?://localhost:\d+|file://)[^"\']*["\']',
        lambda m: f'{m.group(1)}="#"',
        html,
    )

    (pkg_dir / "index.html").write_text(html, encoding="utf-8")

    zip_path = output_path
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(pkg_dir / "index.html", "index.html")
        for chart_name in sorted(chart_files):
            asset_file = assets_dir / chart_name
            if asset_file.is_file():
                zf.write(asset_file, f"assets/{chart_name}")

    shutil.rmtree(pkg_dir)

    return zip_path
