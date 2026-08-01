from pathlib import Path
import re
import shutil

from fastapi import APIRouter, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse

from app.agent.orchestrator import AgentOrchestrator
from app.agent.run_artifacts import build_web_report_package
from app.core.settings import get_settings
from app.memory.store import MemoryStore
from app.models.schemas import AnalysisRequest, RunResponse
from app.tools.package_integrity import MAX_PACKAGE_BYTES, validate_package_bytes
from app.tools.redaction import redact_local_paths
from app.tools.visual_reports import find_visual_report_artifact

router = APIRouter()

_SAFE_RUN_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

REPORT_ASSET_MEDIA_TYPES = {
    ".html": "text/html",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".svg": "image/svg+xml",
}


@router.post("/runs", response_model=RunResponse)
async def create_run(request: AnalysisRequest) -> RunResponse:
    settings = get_settings()
    store = MemoryStore(settings.resolved_sqlite_path)

    # Validate: project runs must only reference same-project datasets
    if request.project_id and request.dataset_ids:
        for ds_id in request.dataset_ids:
            ds = store.get_dataset(ds_id)
            if ds is None:
                raise HTTPException(status_code=400, detail=f"Dataset not found: {ds_id}")
            if ds.project_id and ds.project_id != request.project_id:
                raise HTTPException(
                    status_code=400,
                    detail=f"Dataset {ds_id} belongs to project {ds.project_id}, not {request.project_id}",
                )

    orchestrator = AgentOrchestrator.from_settings(settings)
    run = await orchestrator.run(request)
    store.record_run(run)
    return run


@router.get("/runs/{run_id}/export")
def export_run_package(run_id: str) -> FileResponse:
    settings = get_settings()
    store = MemoryStore(settings.resolved_sqlite_path)
    run = store.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    manifest_artifact = find_visual_report_artifact(run.artifacts)
    if manifest_artifact is None or manifest_artifact.data is None:
        raise HTTPException(status_code=400, detail="Run has no visual report artifact to export")

    data = manifest_artifact.data
    if "manifest" not in data or "snapshot" not in data:
        raise HTTPException(status_code=400, detail="Visual report artifact is missing manifest/snapshot data")

    from app.models.schemas import ArtifactManifest, ArtifactSnapshot
    from app.tools.exports import export_artifact_package

    data = redact_local_paths(data, workspace_root=settings.resolved_workspace_dir)

    manifest = ArtifactManifest.model_validate(data["manifest"])
    snapshot = ArtifactSnapshot.model_validate(data["snapshot"])

    export_dir = settings.resolved_workspace_dir / "exports"
    filepath = export_artifact_package(
        run_id=run_id,
        title=run.question or "Analysis Report",
        question=run.question,
        project_id=run.project_id,
        manifest=manifest,
        snapshot=snapshot,
        candidate_angles=manifest.candidate_angles,
        output_dir=export_dir,
    )
    return FileResponse(
        path=str(filepath),
        media_type="application/json",
        filename=filepath.name,
        headers={"Content-Disposition": f'attachment; filename="{filepath.name}"'},
    )


@router.delete("/runs/{run_id}")
def delete_run(run_id: str) -> dict:
    """Delete a finished run: database row, events, and on-disk artifacts."""
    if not _SAFE_RUN_ID_RE.fullmatch(run_id):
        raise HTTPException(status_code=400, detail="Invalid run id")

    from app.agent.run_registry import cancel_run

    if cancel_run(run_id):
        raise HTTPException(status_code=409, detail="Run is still active; cancel it first")

    settings = get_settings()
    store = MemoryStore(settings.resolved_sqlite_path)
    if not store.delete_run(run_id):
        raise HTTPException(status_code=404, detail="Run not found")

    run_dir = (settings.resolved_workspace_dir / "artifacts" / run_id).resolve()
    if run_dir.is_relative_to(settings.resolved_workspace_dir.resolve()):
        shutil.rmtree(run_dir, ignore_errors=True)

    return {"deleted": run_id}


@router.get("/runs/{run_id}/web-report-package")
def export_web_report_package(run_id: str) -> FileResponse:
    settings = get_settings()
    store = MemoryStore(settings.resolved_sqlite_path)
    run = store.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    artifacts_dir = (settings.resolved_workspace_dir / "artifacts" / run_id).resolve()
    if not artifacts_dir.is_dir():
        raise HTTPException(status_code=400, detail="Run has no artifacts directory")

    web_report = artifacts_dir / "web_report.html"
    if not web_report.is_file():
        raise HTTPException(status_code=400, detail="Run has no Web Report artifact")

    export_dir = settings.resolved_workspace_dir / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    zip_path = export_dir / f"web_report_package_{run_id}.zip"

    try:
        result_path = build_web_report_package(
            run_id=run_id,
            artifacts_dir=artifacts_dir,
            output_path=zip_path,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return FileResponse(
        path=str(result_path),
        media_type="application/zip",
        filename=f"web_report_{run_id}.zip",
        headers={
            "Content-Disposition": f'attachment; filename="web_report_{run_id}.zip"',
        },
    )


@router.get("/runs/{run_id}/assets/{filename}")
def get_run_report_asset(run_id: str, filename: str) -> Response:
    settings = get_settings()
    store = MemoryStore(settings.resolved_sqlite_path)
    if store.get_run(run_id) is None:
        raise HTTPException(status_code=404, detail="Run not found")

    suffix = Path(filename).suffix.lower()
    media_type = REPORT_ASSET_MEDIA_TYPES.get(suffix)
    if media_type is None:
        raise HTTPException(status_code=400, detail="Unsupported report asset type")

    run_dir = (settings.resolved_workspace_dir / "artifacts" / run_id).resolve()
    asset_path = (run_dir / filename).resolve()
    if asset_path.parent != run_dir:
        raise HTTPException(status_code=400, detail="Invalid report asset path")
    if not asset_path.is_file():
        raise HTTPException(status_code=404, detail="Report asset not found")

    headers = {
        "Content-Disposition": f'inline; filename="{asset_path.name}"',
        "X-Content-Type-Options": "nosniff",
    }
    if suffix == ".html":
        headers["Content-Security-Policy"] = (
            "default-src 'none'; "
            "script-src 'unsafe-inline'; "
            "style-src 'unsafe-inline'; "
            "img-src data: blob: 'self'; "
            "frame-src data: 'self'; "
            "child-src data: 'self'; "
            "font-src data:; "
            "connect-src 'none';"
        )
        html = asset_path.read_text(encoding="utf-8", errors="replace")
        return Response(
            content=_decorate_report_chart_html(html),
            media_type=media_type,
            headers=headers,
        )
    return FileResponse(path=str(asset_path), media_type=media_type, headers=headers)


@router.post("/runs/import-validate")
def import_validate_package(file: UploadFile):
    """Import and validate an exported artifact package JSON file."""
    if not file.filename or not file.filename.endswith(".json"):
        raise HTTPException(status_code=400, detail="File must be a JSON artifact package")

    content = file.file.read(MAX_PACKAGE_BYTES + 1)
    result = validate_package_bytes(content)

    return {
        "valid": result.valid,
        "errors": result.errors,
        "warnings": result.warnings,
        "details": result.details,
        "filename": file.filename,
    }


def _decorate_report_chart_html(html: str) -> str:
    """Adapt generated Plotly HTML to the report reader without changing evidence."""
    if 'id="data-agent-chart-reader"' in html:
        return html
    decoration = r"""
<style id="data-agent-chart-reader">
html, body { margin: 0 !important; min-height: 100%; background: transparent !important; }
body { font-family: Inter, "PingFang SC", "Microsoft YaHei", system-ui, sans-serif !important; }
.plotly-graph-div { width: 100% !important; }
.modebar-container { display: none !important; }
</style>
<script>
(() => {
  const labels = {
    aov: "客单价", average_order_value: "客单价", category: "品类",
    clothing: "服装", electronics: "电子", food: "食品", month: "月份",
    order_share_pct: "订单占比", orders: "订单数", orders_growth: "订单增长率",
    orders_growth_pct: "订单环比", product: "产品", revenue: "营收",
    revenue_growth: "营收增长率", revenue_growth_pct: "营收环比",
    revenue_share_pct: "营收占比", total_orders: "总订单", total_revenue: "总营收"
  };
  const localize = (value) => {
    if (typeof value !== "string") return value;
    const key = value.trim().toLowerCase().replace(/\.(html|png|jpg|jpeg|svg)$/i, "");
    if (labels[key]) return labels[key];
    const month = value.match(/^(\d{4})-(\d{2})$/);
    if (month) return `${month[1]}年${Number(month[2])}月`;
    return value.replace(/\b[a-z][a-z0-9_]*\b/gi, (token) => labels[token.toLowerCase()] || token.replace(/_/g, " "));
  };
  const localizeArray = (value) => Array.isArray(value) ? value.map(localize) : value;
  const apply = () => {
    if (!window.Plotly) return;
    document.querySelectorAll(".plotly-graph-div").forEach((graph) => {
      const data = (graph.data || []).map((trace) => ({
        ...trace,
        name: localize(trace.name),
        labels: localizeArray(trace.labels),
        text: localizeArray(trace.text),
        hovertemplate: localize(trace.hovertemplate)
      }));
      const layout = { ...(graph.layout || {}) };
      layout.title = { ...(layout.title || {}), text: "" };
      layout.margin = { ...(layout.margin || {}), t: 18, l: Math.max(layout.margin?.l || 0, 54), r: 24, b: Math.max(layout.margin?.b || 0, 48) };
      layout.paper_bgcolor = "rgba(0,0,0,0)";
      layout.plot_bgcolor = "rgba(0,0,0,0)";
      layout.font = { ...(layout.font || {}), family: 'Inter, "PingFang SC", "Microsoft YaHei", system-ui, sans-serif', color: "#334155" };
      ["xaxis", "yaxis"].forEach((axisName) => {
        const axis = { ...(layout[axisName] || {}) };
        const title = typeof axis.title === "string" ? axis.title : axis.title?.text;
        axis.title = { ...(typeof axis.title === "object" ? axis.title : {}), text: localize(title || "") };
        const coordinate = axisName === "xaxis" ? "x" : "y";
        const values = data.flatMap((trace) => Array.isArray(trace[coordinate]) ? trace[coordinate] : []);
        const stringValues = values.filter((value) => typeof value === "string");
        const dateLike = stringValues.some((value) => /^\d{4}-\d{2}(-\d{2})?/.test(value));
        if (dateLike || axis.type === "date") {
          const uniqueValues = [...new Set(stringValues)];
          const discretePeriods = uniqueValues.length > 0 && uniqueValues.length <= 24
            && uniqueValues.every((value) => /^\d{4}-\d{2}(-\d{2})?$/.test(value));
          if (discretePeriods) {
            axis.type = "category";
            axis.categoryorder = "array";
            axis.categoryarray = uniqueValues;
            axis.tickvals = uniqueValues;
            axis.ticktext = uniqueValues.map(localize);
          } else {
            axis.tickformat = "%Y年%m月";
            axis.hoverformat = "%Y年%m月";
          }
        } else if (stringValues.length) {
          const uniqueValues = [...new Set(stringValues)];
          axis.tickvals = uniqueValues;
          axis.ticktext = uniqueValues.map(localize);
        } else if (axis.ticktext) {
          axis.ticktext = localizeArray(axis.ticktext);
        }
        axis.gridcolor = "#e5e7eb";
        axis.zerolinecolor = "#cbd5e1";
        layout[axisName] = axis;
      });
      window.Plotly.react(graph, data, layout, { responsive: true, displayModeBar: false, locale: "zh-CN" });
    });
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", () => setTimeout(apply, 0), { once: true });
  else setTimeout(apply, 0);
})();
</script>
"""
    lower_html = html.lower()
    body_index = lower_html.rfind("</body>")
    if body_index >= 0:
        return html[:body_index] + decoration + html[body_index:]
    return html + decoration
