import hashlib
import json

from app.tools.package_integrity import validate_package_data
from app.models.schemas import ArtifactManifest, ArtifactSnapshot


def _checksum(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _package():
    manifest = ArtifactManifest(title="Demo")
    snapshot = ArtifactSnapshot()
    return {
        "package_version": 1,
        "title": "Demo",
        "generated_at": "2024-01-01T00:00:00Z",
        "manifest": manifest.model_dump(mode="json"),
        "snapshot": snapshot.model_dump(mode="json"),
        "metadata": {
            "manifest_checksum": _checksum(manifest.model_dump(mode="json")),
            "snapshot_checksum": _checksum(snapshot.model_dump(mode="json")),
        },
    }


def test_validate_package_data_accepts_valid_checksums():
    result = validate_package_data(_package())
    assert result.valid is True
    assert result.errors == []
    assert result.details["manifest_checksum_ok"] is True
    assert result.details["snapshot_checksum_ok"] is True


def test_validate_package_data_rejects_missing_checksums():
    package = _package()
    package["metadata"] = {}
    result = validate_package_data(package)
    assert result.valid is False
    assert "Missing manifest_checksum" in result.errors[0]
    assert "Missing snapshot_checksum" in result.errors[1]


def test_validate_package_data_rejects_checksum_mismatch():
    package = _package()
    package["manifest"]["title"] = "Tampered"
    result = validate_package_data(package)
    assert result.valid is False
    assert any("Manifest checksum mismatch" in e for e in result.errors)
