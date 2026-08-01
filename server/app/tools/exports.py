import hashlib
import json
from pathlib import Path

from app.models.schemas import ArtifactManifest, ArtifactPackage, ArtifactSnapshot


def export_artifact_package(
    run_id: str,
    title: str,
    question: str | None,
    project_id: str | None,
    manifest: ArtifactManifest,
    snapshot: ArtifactSnapshot,
    output_dir: Path | None = None,
    candidate_angles: list[dict] | None = None,
) -> Path:
    import datetime as dt

    now = dt.datetime.now(dt.UTC).isoformat()

    package = ArtifactPackage(
        title=title,
        generated_at=now,
        project_id=project_id,
        question=question,
        manifest=manifest,
        snapshot=snapshot,
        metadata={
            "run_id": run_id,
            "exported_at": now,
            "app_version": "0.1.0",
            "package_schema_version": 1,
            "manifest_version": manifest.version,
            "snapshot_version": snapshot.version,
            "manifest_checksum": hashlib.sha256(
                json.dumps(manifest.model_dump(mode="json"), sort_keys=True).encode()
            ).hexdigest(),
            "snapshot_checksum": hashlib.sha256(
                json.dumps(snapshot.model_dump(mode="json"), sort_keys=True).encode()
            ).hexdigest(),
            "chart_count": len(manifest.charts),
            "table_count": len(manifest.tables),
            "block_count": len(manifest.blocks),
            "source_count": len(manifest.sources),
            "dataset_count": len(snapshot.datasets),
            "candidate_angles": candidate_angles if candidate_angles else manifest.candidate_angles,
        },
    )

    target_dir = output_dir or Path("workspace/exports")
    target_dir.mkdir(parents=True, exist_ok=True)
    filename = f"artifact-package-{run_id[:8]}.json"
    filepath = target_dir / filename

    filepath.write_text(package.model_dump_json(indent=2), encoding="utf-8")
    return filepath


def import_artifact_package(filepath: Path) -> ArtifactPackage:
    """Read and validate an exported artifact package.

    Returns the validated ArtifactPackage, or raises ValueError for
    structural issues (corrupted manifest, missing snapshot, checksum mismatch).
    """
    if not filepath.exists():
        raise ValueError(f"Package file not found: {filepath}")

    try:
        data = json.loads(filepath.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise ValueError(f"Package file is corrupted (not valid JSON): {e}")

    if "manifest" not in data:
        raise ValueError("Package missing 'manifest' key")
    if "snapshot" not in data:
        raise ValueError("Package missing 'snapshot' key")

    # Validate checksums
    manifest = ArtifactManifest.model_validate(data["manifest"])
    snapshot = ArtifactSnapshot.model_validate(data["snapshot"])
    meta = data.get("metadata", {})

    expected_manifest_checksum = hashlib.sha256(
        json.dumps(manifest.model_dump(mode="json"), sort_keys=True).encode()
    ).hexdigest()
    expected_snapshot_checksum = hashlib.sha256(
        json.dumps(snapshot.model_dump(mode="json"), sort_keys=True).encode()
    ).hexdigest()

    if meta.get("manifest_checksum") != expected_manifest_checksum:
        raise ValueError("Manifest checksum mismatch — package may be corrupted")
    if meta.get("snapshot_checksum") != expected_snapshot_checksum:
        raise ValueError("Snapshot checksum mismatch — package may be corrupted")

    return ArtifactPackage.model_validate(data)
