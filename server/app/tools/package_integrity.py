"""Package integrity validation — verify exported artifact packages."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.models.schemas import ArtifactPackage

MAX_PACKAGE_BYTES = 50 * 1024 * 1024


@dataclass(frozen=True)
class PackageValidationResult:
    valid: bool
    errors: list[str]
    warnings: list[str]
    details: dict[str, Any] | None = None


def _stable_hash(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def validate_package_bytes(
    content: bytes,
    *,
    max_bytes: int = MAX_PACKAGE_BYTES,
) -> PackageValidationResult:
    """Validate uploaded artifact package bytes without requiring a temp file."""
    size_bytes = len(content)
    if size_bytes > max_bytes:
        max_mb = max_bytes // (1024 * 1024)
        return PackageValidationResult(
            valid=False,
            errors=[f"Package file too large. Max package size is {max_mb} MB"],
            warnings=[],
            details={"size_bytes": size_bytes, "max_bytes": max_bytes},
        )

    try:
        data = json.loads(content.decode("utf-8"))
    except json.JSONDecodeError as e:
        return PackageValidationResult(valid=False, errors=[f"Invalid JSON: {e}"], warnings=[])
    except UnicodeDecodeError as e:
        return PackageValidationResult(valid=False, errors=[f"Invalid UTF-8: {e}"], warnings=[])

    return validate_package_data(data)


def validate_package_data(data: Any) -> PackageValidationResult:
    """Validate an already-parsed artifact package for schema and integrity."""
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(data, dict):
        return PackageValidationResult(
            valid=False,
            errors=["Package root must be a JSON object"],
            warnings=warnings,
        )

    required = ["package_version", "manifest", "snapshot", "metadata"]
    for field in required:
        if field not in data:
            errors.append(f"Missing required field: {field}")

    if errors:
        return PackageValidationResult(valid=False, errors=errors, warnings=warnings)

    try:
        package = ArtifactPackage.model_validate(data)
    except ValidationError as exc:
        schema_errors = [
            f"Invalid package schema at {'.'.join(str(part) for part in err['loc'])}: {err['msg']}"
            for err in exc.errors()
        ]
        return PackageValidationResult(valid=False, errors=schema_errors, warnings=warnings)

    metadata = package.metadata
    manifest = package.manifest.model_dump(mode="json")
    snapshot = package.snapshot.model_dump(mode="json")

    stored_manifest_hash = metadata.get("manifest_checksum")
    stored_snapshot_hash = metadata.get("snapshot_checksum")
    manifest_ok = False
    snapshot_ok = False

    if not stored_manifest_hash:
        errors.append("Missing manifest_checksum in package metadata")
    else:
        expected_manifest_hash = _stable_hash(manifest)
        manifest_ok = stored_manifest_hash == expected_manifest_hash
        if not manifest_ok:
            errors.append("Manifest checksum mismatch — data may be corrupted")

    if not stored_snapshot_hash:
        errors.append("Missing snapshot_checksum in package metadata")
    else:
        expected_snapshot_hash = _stable_hash(snapshot)
        snapshot_ok = stored_snapshot_hash == expected_snapshot_hash
        if not snapshot_ok:
            errors.append("Snapshot checksum mismatch — data may be corrupted")

    pkg_version = package.package_version
    if pkg_version != 1:
        warnings.append(f"Unknown package_version: {pkg_version}")

    return PackageValidationResult(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        details={
            "package_version": pkg_version,
            "manifest_checksum_ok": manifest_ok,
            "snapshot_checksum_ok": snapshot_ok,
        },
    )


def validate_exported_package(
    package_path: str | Path,
    *,
    max_bytes: int = MAX_PACKAGE_BYTES,
) -> PackageValidationResult:
    """Validate an exported artifact package file for schema and integrity."""
    path = Path(package_path)

    if not path.exists():
        return PackageValidationResult(valid=False, errors=["Package file not found"], warnings=[])

    try:
        size_bytes = path.stat().st_size
    except OSError as exc:
        return PackageValidationResult(valid=False, errors=[f"Unable to stat package file: {exc}"], warnings=[])

    if size_bytes > max_bytes:
        max_mb = max_bytes // (1024 * 1024)
        return PackageValidationResult(
            valid=False,
            errors=[f"Package file too large. Max package size is {max_mb} MB"],
            warnings=[],
            details={"size_bytes": size_bytes, "max_bytes": max_bytes},
        )

    try:
        content = path.read_bytes()
    except OSError as exc:
        return PackageValidationResult(valid=False, errors=[f"Unable to read package file: {exc}"], warnings=[])

    return validate_package_bytes(content, max_bytes=max_bytes)
