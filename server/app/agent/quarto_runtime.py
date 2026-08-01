from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.settings import Settings

logger = logging.getLogger(__name__)

_MANAGED_BASE = Path.home() / ".cache" / "data-agent" / "quarto"


@dataclass(frozen=True)
class QuartoRuntime:
    available: bool
    path: Path | None
    version: str | None
    source: str
    message: str


def find_quarto_runtime(settings: Settings | None = None) -> QuartoRuntime:
    resolution_order = [
        _try_explicit_path,
        _try_managed_path,
        _try_system_path,
    ]

    for resolver in resolution_order:
        runtime = resolver(settings)
        if runtime is not None:
            logger.info("quarto_runtime_resolved: source=%s path=%s version=%s",
                        runtime.source, runtime.path, runtime.version)
            return runtime

    return QuartoRuntime(
        available=False,
        path=None,
        version=None,
        source="missing",
        message="Quarto CLI not found. Install Quarto or set DATA_AGENT_QUARTO_BIN.",
    )


def _try_explicit_path(settings: Settings | None) -> QuartoRuntime | None:
    if settings is None or settings.quarto_bin is None:
        return None
    bin_path = Path(settings.quarto_bin).expanduser().resolve()
    return _validate_binary(bin_path, "explicit")


def _try_managed_path(settings: Settings | None) -> QuartoRuntime | None:
    version = settings.quarto_version if settings else "1.9.38"
    bin_path = _MANAGED_BASE / version / "bin" / "quarto"
    return _validate_binary(bin_path, "managed")


def _try_system_path(_settings: Settings | None = None) -> QuartoRuntime | None:
    which = shutil.which("quarto")
    if which is None:
        return None
    return _validate_binary(Path(which), "system")


def _validate_binary(bin_path: Path, source: str) -> QuartoRuntime | None:
    if not bin_path.is_file():
        if source == "explicit":
            return QuartoRuntime(
                available=False,
                path=None,
                version=None,
                source=source,
                message=f"Quarto binary not found at configured path: {bin_path}",
            )
        return None

    try:
        result = subprocess.run(
            [str(bin_path), "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (subprocess.TimeoutExpired, OSError) as e:
        return QuartoRuntime(
            available=False,
            path=None,
            version=None,
            source=source,
            message=f"Quarto binary failed to execute: {e}",
        )

    if result.returncode != 0:
        return QuartoRuntime(
            available=False,
            path=None,
            version=None,
            source=source,
            message=f"Quarto binary returned non-zero exit code: {result.returncode}",
        )

    version = result.stdout.strip().splitlines()[0].strip()
    return QuartoRuntime(
        available=True,
        path=bin_path,
        version=version,
        source=source,
        message="Quarto CLI is available.",
    )
