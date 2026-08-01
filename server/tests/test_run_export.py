import json
import tempfile
from pathlib import Path

import pytest

from app.memory.store import MemoryStore
from app.models.schemas import (
    Artifact,
    ArtifactBlock,
    ArtifactBlockType,
    ArtifactManifest,
    ArtifactSnapshot,
    ArtifactType,
    RunResponse,
)
from app.tools.exports import export_artifact_package, import_artifact_package
from app.tools.package_integrity import validate_exported_package, validate_package_bytes, validate_package_data


def _make_manifest() -> ArtifactManifest:
    return ArtifactManifest(
        title="Test Report",
        blocks=[
            ArtifactBlock(id="b1", type=ArtifactBlockType.markdown, body="# Summary"),
            ArtifactBlock(id="b2", type=ArtifactBlockType.chart, chart_id="c1"),
        ],
    )


def _make_snapshot() -> ArtifactSnapshot:
    return ArtifactSnapshot(
        datasets={"ds_c1": [{"month": "Jan", "revenue": 1000}]},
    )


def _make_run_with_manifest(run_id: str) -> RunResponse:
    manifest = _make_manifest()
    snapshot = _make_snapshot()
    return RunResponse(
        id=run_id,
        status="completed",
        skill_id="test_skill",
        question="What is revenue?",
        project_id="proj_1",
        artifacts=[
            Artifact(
                type=ArtifactType.visual_report,
                title="图文分析报告",
                data={
                    "manifest": manifest.model_dump(mode="json"),
                    "snapshot": snapshot.model_dump(mode="json"),
                },
            ),
        ],
    )


class TestExportArtifactPackage:
    def test_export_creates_valid_json_file(self):
        manifest = _make_manifest()
        snapshot = _make_snapshot()
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir)
            filepath = export_artifact_package(
                run_id="abc12345",
                title="Revenue Analysis",
                question="What is revenue?",
                project_id="proj_1",
                manifest=manifest,
                snapshot=snapshot,
                output_dir=out,
            )
            assert filepath.exists()
            assert filepath.suffix == ".json"

            data = json.loads(filepath.read_text(encoding="utf-8"))
            assert data["package_version"] == 1
            assert data["title"] == "Revenue Analysis"
            assert "id" in data
            assert "generated_at" in data

    def test_export_package_contains_manifest_snapshot_metadata(self):
        manifest = _make_manifest()
        snapshot = _make_snapshot()
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir)
            filepath = export_artifact_package(
                run_id="test1234",
                title="Test Export",
                question=None,
                project_id=None,
                manifest=manifest,
                snapshot=snapshot,
                output_dir=out,
            )
            data = json.loads(filepath.read_text(encoding="utf-8"))

            assert "manifest" in data
            assert "snapshot" in data
            assert "metadata" in data
            assert data["manifest"]["title"] == "Test Report"
            assert data["manifest"]["version"] == 1
            assert data["snapshot"]["version"] == 1
            assert data["metadata"]["run_id"] == "test1234"
            assert data["metadata"]["block_count"] == 2
            assert data["metadata"]["chart_count"] == 0
            assert data["metadata"]["dataset_count"] == 1

    def test_export_default_output_dir(self):
        manifest = _make_manifest()
        snapshot = _make_snapshot()
        filepath = export_artifact_package(
            run_id="default1",
            title="Default Dir Test",
            question=None,
            project_id=None,
            manifest=manifest,
            snapshot=snapshot,
        )
        try:
            assert filepath.exists()
            assert filepath.name.startswith("artifact-package-default1")
            data = json.loads(filepath.read_text(encoding="utf-8"))
            assert data["title"] == "Default Dir Test"
        finally:
            filepath.unlink(missing_ok=True)

    def test_export_includes_checksums(self):
        """Export metadata includes manifest and snapshot checksums."""
        manifest = _make_manifest()
        snapshot = _make_snapshot()
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir)
            filepath = export_artifact_package(
                run_id="checksum01",
                title="Checksum Test",
                question=None,
                project_id=None,
                manifest=manifest,
                snapshot=snapshot,
                output_dir=out,
            )
            data = json.loads(filepath.read_text(encoding="utf-8"))
            meta = data["metadata"]
            assert "manifest_checksum" in meta
            assert "snapshot_checksum" in meta
            assert len(meta["manifest_checksum"]) == 64  # SHA-256 hex
            assert len(meta["snapshot_checksum"]) == 64
            assert meta["app_version"] == "0.1.0"
            assert meta["package_schema_version"] == 1

    def test_package_validation_detects_corruption(self, tmp_path):
        """validate_exported_package detects checksum mismatch."""
        manifest = _make_manifest()
        snapshot = _make_snapshot()
        export_artifact_package(
            run_id="val001",
            title="Validation Test",
            question=None,
            project_id=None,
            manifest=manifest,
            snapshot=snapshot,
            output_dir=tmp_path,
        )
        # The exported file uses run_id prefix, find it
        exported = list(tmp_path.glob("artifact-package-*.json"))[0]
        result = validate_exported_package(exported)
        assert result.valid, f"Expected valid, got errors: {result.errors}"

        # Corrupt the manifest
        data = json.loads(exported.read_text(encoding="utf-8"))
        data["manifest"]["title"] = "CORRUPTED"
        exported.write_text(json.dumps(data), encoding="utf-8")
        result = validate_exported_package(exported)
        assert not result.valid
        assert any("checksum" in e.lower() for e in result.errors)

    def test_package_validation_rejects_non_object_root(self):
        result = validate_package_data(["not", "an", "object"])
        assert not result.valid
        assert "root must be a JSON object" in result.errors[0]

    def test_package_validation_rejects_invalid_manifest_schema_even_with_metadata(self, tmp_path):
        manifest = _make_manifest()
        snapshot = _make_snapshot()
        exported = export_artifact_package(
            run_id="schema01",
            title="Schema Validation Test",
            question=None,
            project_id=None,
            manifest=manifest,
            snapshot=snapshot,
            output_dir=tmp_path,
        )
        data = json.loads(exported.read_text(encoding="utf-8"))
        data["manifest"].pop("title")

        result = validate_package_data(data)
        assert not result.valid
        assert any("manifest.title" in error for error in result.errors)

    def test_package_validation_rejects_oversized_file_before_reading_json(self, tmp_path):
        package_path = tmp_path / "too-large.json"
        package_path.write_text("{not-json", encoding="utf-8")

        result = validate_exported_package(package_path, max_bytes=1)

        assert not result.valid
        assert any("too large" in error.lower() for error in result.errors)
        assert result.details == {"size_bytes": package_path.stat().st_size, "max_bytes": 1}

    def test_package_validation_rejects_oversized_bytes_before_json_parse(self):
        result = validate_package_bytes(b"{not-json", max_bytes=1)

        assert not result.valid
        assert any("too large" in error.lower() for error in result.errors)
        assert result.details == {"size_bytes": 9, "max_bytes": 1}

    def test_package_validation_rejects_invalid_utf8_bytes(self):
        result = validate_package_bytes(b"\xff")

        assert not result.valid
        assert any("utf-8" in error.lower() for error in result.errors)

    def test_package_validation_missing_file(self, tmp_path):
        """validate_exported_package returns error for missing file."""
        result = validate_exported_package(tmp_path / "nonexistent.json")
        assert not result.valid
        assert any("not found" in e.lower() for e in result.errors)

    def test_import_artifact_package_roundtrip(self, tmp_path):
        """Export then import — checksums match and package is valid."""
        manifest = _make_manifest()
        snapshot = _make_snapshot()
        filepath = export_artifact_package(
            run_id="import01", title="Import Test", question=None,
            project_id=None, manifest=manifest, snapshot=snapshot,
            output_dir=tmp_path,
        )
        pkg = import_artifact_package(filepath)
        assert pkg.title == "Import Test"
        assert pkg.manifest.title == "Test Report"
        assert pkg.metadata["manifest_checksum"] is not None

    def test_import_artifact_package_corrupted_manifest(self, tmp_path):
        """Import detects checksum mismatch after manifest tampering."""
        manifest = _make_manifest()
        snapshot = _make_snapshot()
        filepath = export_artifact_package(
            run_id="corrupt1", title="Corrupt Test", question=None,
            project_id=None, manifest=manifest, snapshot=snapshot,
            output_dir=tmp_path,
        )
        data = json.loads(filepath.read_text(encoding="utf-8"))
        data["manifest"]["title"] = "TAMPERED"
        filepath.write_text(json.dumps(data), encoding="utf-8")
        with pytest.raises(ValueError, match="checksum"):
            import_artifact_package(filepath)

    def test_import_artifact_package_missing_file(self, tmp_path):
        with pytest.raises(ValueError, match="not found"):
            import_artifact_package(tmp_path / "ghost.json")


class TestExportEndpointIntegration:
    def test_run_with_manifest_roundtrip(self):
        run_id = "run-export-test-001"
        run = _make_run_with_manifest(run_id)

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.sqlite"
            store = MemoryStore(db_path)
            store.record_run(run)

            retrieved = store.get_run(run_id)
            assert retrieved is not None
            assert len(retrieved.artifacts) == 1

            manifest_artifact = None
            for a in retrieved.artifacts:
                if a.type == ArtifactType.visual_report:
                    manifest_artifact = a
                    break
            assert manifest_artifact is not None
            assert manifest_artifact.data is not None

            manifest_data = manifest_artifact.data["manifest"]
            snapshot_data = manifest_artifact.data["snapshot"]
            assert manifest_data["title"] == "Test Report"
            assert len(snapshot_data["datasets"]) == 1

            manifest = ArtifactManifest.model_validate(manifest_data)
            snapshot = ArtifactSnapshot.model_validate(snapshot_data)

            filepath = export_artifact_package(
                run_id=run_id,
                title=retrieved.question or "Fallback",
                question=retrieved.question,
                project_id=retrieved.project_id,
                manifest=manifest,
                snapshot=snapshot,
                output_dir=Path(tmpdir) / "exports",
            )
            assert filepath.exists()
            package = json.loads(filepath.read_text(encoding="utf-8"))
            assert package["question"] == "What is revenue?"
            assert package["manifest"]["title"] == "Test Report"

    def test_run_without_manifest_raises(self):
        run = RunResponse(
            id="no-manifest",
            status="completed",
            skill_id="test_skill",
            question="No manifest here",
            artifacts=[Artifact(type=ArtifactType.chart, title="some_chart")],
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.sqlite"
            store = MemoryStore(db_path)
            store.record_run(run)

            retrieved = store.get_run(run_id="no-manifest")
            assert retrieved is not None

            manifest_artifact = None
            for a in retrieved.artifacts:
                if a.type == ArtifactType.visual_report:
                    manifest_artifact = a
                    break
            assert manifest_artifact is None
