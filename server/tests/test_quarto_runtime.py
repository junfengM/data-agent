"""Tests for quarto_runtime — Quarto binary discovery and validation."""
from __future__ import annotations

import subprocess
from pathlib import Path
from unittest import mock

from app.agent.quarto_runtime import (
    QuartoRuntime,
    find_quarto_runtime,
)
from app.core.settings import Settings


# ── Explicit path resolution ────────────────────────────────────────────────

class TestExplicitPathResolution:
    def test_valid_explicit_path_wins(self, tmp_path):
        """Explicit DATA_AGENT_QUARTO_BIN wins when binary is valid."""
        bin_path = tmp_path / "my-quarto"
        settings = Settings(quarto_bin=str(bin_path))

        with mock.patch("shutil.which", return_value="/usr/bin/quarto"):
            with mock.patch.object(Path, "is_file", return_value=True):
                with mock.patch("subprocess.run") as mock_run:
                    mock_run.return_value.returncode = 0
                    mock_run.return_value.stdout = "1.9.38\n"

                    result = find_quarto_runtime(settings)

        assert result.available is True
        assert result.source == "explicit"
        assert result.path == bin_path.resolve()
        assert result.version == "1.9.38"
        assert result.message == "Quarto CLI is available."

    def test_invalid_explicit_path_returns_unavailable(self):
        """Explicit path with missing binary returns unavailable with helpful message."""
        settings = Settings(quarto_bin="/nonexistent/quarto")

        with mock.patch.object(Path, "is_file", return_value=False):
            result = find_quarto_runtime(settings)

        assert result.available is False
        assert result.source == "explicit"
        assert result.path is None
        assert result.version is None
        assert "not found at configured path" in result.message
        assert "/nonexistent/quarto" in result.message

    def test_explicit_path_non_executable(self):
        """Explicit path exists but fails to execute (OSError)."""
        settings = Settings(quarto_bin="/broken/quarto")

        with mock.patch.object(Path, "is_file", return_value=True):
            with mock.patch("subprocess.run", side_effect=OSError("Permission denied")):
                result = find_quarto_runtime(settings)

        assert result.available is False
        assert result.source == "explicit"
        assert result.path is None
        assert result.version is None
        assert "Permission denied" in result.message

    def test_explicit_path_binary_missing_file(self):
        """Explicit path where the file simply doesn't exist."""
        settings = Settings(quarto_bin="/ghost/quarto")

        with mock.patch.object(Path, "is_file", return_value=False):
            result = find_quarto_runtime(settings)

        assert result.available is False
        assert result.source == "explicit"
        assert "/ghost/quarto" in result.message


# ── Managed path resolution ─────────────────────────────────────────────────

class TestManagedPathResolution:
    def test_managed_path_detected_when_binary_exists(self, tmp_path):
        """Managed Quarto is detected when binary exists under managed base."""
        managed_base = tmp_path / "managed-base"
        bin_path = managed_base / "1.9.38" / "bin" / "quarto"

        with mock.patch("app.agent.quarto_runtime._MANAGED_BASE", managed_base):
            with mock.patch("shutil.which", return_value=None):
                with mock.patch.object(Path, "is_file", return_value=True):
                    with mock.patch("subprocess.run") as mock_run:
                        mock_run.return_value.returncode = 0
                        mock_run.return_value.stdout = "1.9.38\n"

                        result = find_quarto_runtime(None)

        assert result.available is True
        assert result.source == "managed"
        assert result.path == bin_path
        assert result.version == "1.9.38"

    def test_default_version_used_when_settings_is_none(self, tmp_path):
        """Default version '1.9.38' is used for managed path when settings is None."""
        managed_base = tmp_path / "managed-base"
        expected_bin_path = managed_base / "1.9.38" / "bin" / "quarto"

        with mock.patch("app.agent.quarto_runtime._MANAGED_BASE", managed_base):
            with mock.patch("shutil.which", return_value=None):
                with mock.patch.object(Path, "is_file", return_value=True):
                    with mock.patch("subprocess.run") as mock_run:
                        mock_run.return_value.returncode = 0
                        mock_run.return_value.stdout = "1.9.38\n"

                        find_quarto_runtime(None)

        # Verify subprocess was called with the default version path
        call_args = mock_run.call_args[0][0]
        assert str(expected_bin_path) in call_args[0]

    def test_custom_version_from_settings(self, tmp_path):
        """Settings.quarto_version overrides the default managed version."""
        managed_base = tmp_path / "managed-base"
        expected_bin_path = managed_base / "2.0.0" / "bin" / "quarto"
        settings = Settings(quarto_version="2.0.0")

        with mock.patch("app.agent.quarto_runtime._MANAGED_BASE", managed_base):
            with mock.patch("shutil.which", return_value=None):
                with mock.patch.object(Path, "is_file", return_value=True):
                    with mock.patch("subprocess.run") as mock_run:
                        mock_run.return_value.returncode = 0
                        mock_run.return_value.stdout = "2.0.0\n"

                        result = find_quarto_runtime(settings)

        call_args = mock_run.call_args[0][0]
        assert str(expected_bin_path) in call_args[0]
        assert result.source == "managed"
        assert result.version == "2.0.0"

    def test_managed_path_binary_missing(self, tmp_path):
        """When managed binary doesn't exist, fall through to next resolver."""
        managed_base = tmp_path / "managed-base"

        with mock.patch("app.agent.quarto_runtime._MANAGED_BASE", managed_base):
            with mock.patch("shutil.which", return_value=None):
                with mock.patch.object(Path, "is_file", return_value=False):
                    result = find_quarto_runtime(None)

        # Falls through to missing
        assert result.source == "missing"
        assert result.available is False


# ── System PATH resolution ──────────────────────────────────────────────────

class TestSystemPathResolution:
    def test_system_path_found_via_which(self):
        """Quarto found on system PATH via shutil.which."""
        with mock.patch(
            "app.agent.quarto_runtime._try_managed_path", return_value=None
        ):
            with mock.patch("shutil.which", return_value="/usr/local/bin/quarto"):
                with mock.patch.object(Path, "is_file", return_value=True):
                    with mock.patch("subprocess.run") as mock_run:
                        mock_run.return_value.returncode = 0
                        mock_run.return_value.stdout = "1.8.0\n"

                        result = find_quarto_runtime(None)

        assert result.available is True
        assert result.source == "system"
        assert result.path == Path("/usr/local/bin/quarto")
        assert result.version == "1.8.0"

    def test_system_path_no_quarto_on_path(self):
        """When shutil.which returns None, system resolver yields None."""
        with mock.patch(
            "app.agent.quarto_runtime._try_managed_path", return_value=None
        ):
            with mock.patch("shutil.which", return_value=None):
                result = find_quarto_runtime(None)

        assert result.source == "missing"
        assert result.available is False


# ── Missing Quarto ──────────────────────────────────────────────────────────

class TestMissingQuarto:
    def test_missing_quarto_returns_unavailable(self):
        """When no resolver finds Quarto, source='missing' with helpful message."""
        with mock.patch("shutil.which", return_value=None):
            with mock.patch.object(Path, "is_file", return_value=False):
                result = find_quarto_runtime(None)

        assert result.available is False
        assert result.source == "missing"
        assert result.path is None
        assert result.version is None
        assert "Quarto CLI not found" in result.message
        assert "DATA_AGENT_QUARTO_BIN" in result.message


# ── Binary validation edge cases ────────────────────────────────────────────

class TestBinaryValidation:
    def test_non_zero_exit_code_returns_unavailable(self):
        """Binary that returns non-zero exit code on --version is unavailable."""
        with mock.patch(
            "app.agent.quarto_runtime._try_managed_path", return_value=None
        ):
            with mock.patch("shutil.which", return_value="/usr/bin/quarto"):
                with mock.patch.object(Path, "is_file", return_value=True):
                    with mock.patch("subprocess.run") as mock_run:
                        mock_run.return_value.returncode = 127
                        mock_run.return_value.stdout = ""

                        result = find_quarto_runtime(None)

        assert result.available is False
        assert result.source == "system"
        assert result.path is None
        assert result.version is None
        assert "non-zero exit code" in result.message
        assert "127" in result.message

    def test_timeout_returns_unavailable(self):
        """Binary that times out on --version is unavailable."""
        with mock.patch(
            "app.agent.quarto_runtime._try_managed_path", return_value=None
        ):
            with mock.patch("shutil.which", return_value="/usr/bin/quarto"):
                with mock.patch.object(Path, "is_file", return_value=True):
                    with mock.patch(
                        "subprocess.run",
                        side_effect=subprocess.TimeoutExpired(cmd="quarto", timeout=10),
                    ):
                        result = find_quarto_runtime(None)

        assert result.available is False
        assert result.source == "system"
        assert result.path is None
        assert result.version is None
        assert "failed to execute" in result.message

    def test_oserror_on_execution_returns_unavailable(self):
        """Binary that raises OSError on execution is unavailable."""
        with mock.patch(
            "app.agent.quarto_runtime._try_managed_path", return_value=None
        ):
            with mock.patch("shutil.which", return_value="/usr/bin/quarto"):
                with mock.patch.object(Path, "is_file", return_value=True):
                    with mock.patch(
                        "subprocess.run",
                        side_effect=OSError("Exec format error"),
                    ):
                        result = find_quarto_runtime(None)

        assert result.available is False
        assert result.source == "system"
        assert result.path is None
        assert result.version is None
        assert "Exec format error" in result.message


# ── Resolution order ────────────────────────────────────────────────────────

class TestResolutionOrder:
    def test_explicit_wins_over_managed_and_system(self, tmp_path):
        """Resolution order: explicit > managed > system."""
        bin_path = tmp_path / "explicit-quarto"
        settings = Settings(quarto_bin=str(bin_path))
        managed_base = tmp_path / "managed-base"

        with mock.patch("app.agent.quarto_runtime._MANAGED_BASE", managed_base):
            with mock.patch("shutil.which", return_value="/usr/bin/quarto"):
                with mock.patch.object(Path, "is_file", return_value=True):
                    with mock.patch("subprocess.run") as mock_run:
                        mock_run.return_value.returncode = 0
                        mock_run.return_value.stdout = "explicit-version\n"

                        result = find_quarto_runtime(settings)

        assert result.source == "explicit"
        assert result.path == bin_path.resolve()
        assert result.version == "explicit-version"

    def test_managed_wins_over_system_when_no_explicit(self, tmp_path):
        """Resolution order: managed > system when no explicit path set."""
        managed_base = tmp_path / "managed-base"
        expected_path = managed_base / "1.9.38" / "bin" / "quarto"

        with mock.patch("app.agent.quarto_runtime._MANAGED_BASE", managed_base):
            with mock.patch("shutil.which", return_value="/usr/bin/quarto"):
                with mock.patch.object(Path, "is_file", return_value=True):
                    with mock.patch("subprocess.run") as mock_run:
                        mock_run.return_value.returncode = 0
                        mock_run.return_value.stdout = "managed-version\n"

                        result = find_quarto_runtime(None)

        assert result.source == "managed"
        assert result.path == expected_path
        assert result.version == "managed-version"

    def test_system_wins_when_explicit_and_managed_fail(self):
        """Resolution order: system wins when explicit unset and managed fails."""
        with mock.patch(
            "app.agent.quarto_runtime._try_managed_path", return_value=None
        ):
            with mock.patch("shutil.which", return_value="/usr/local/bin/quarto"):
                with mock.patch.object(Path, "is_file", return_value=True):
                    with mock.patch("subprocess.run") as mock_run:
                        mock_run.return_value.returncode = 0
                        mock_run.return_value.stdout = "system-version\n"

                        result = find_quarto_runtime(None)

        assert result.source == "system"
        assert result.path == Path("/usr/local/bin/quarto")
        assert result.version == "system-version"

    def test_all_fail_returns_missing(self):
        """When all resolvers fail, source='missing'."""
        with mock.patch("shutil.which", return_value=None):
            with mock.patch.object(Path, "is_file", return_value=False):
                result = find_quarto_runtime(None)

        assert result.source == "missing"
        assert result.available is False


# ── QuartoRuntime dataclass properties ──────────────────────────────────────

class TestQuartoRuntimeProperties:
    def test_frozen_dataclass_prevents_mutation(self):
        rt = QuartoRuntime(
            available=True,
            path=Path("/usr/bin/quarto"),
            version="1.9.38",
            source="system",
            message="OK",
        )
        import dataclasses
        with __import__("pytest").raises(dataclasses.FrozenInstanceError):
            rt.available = False  # type: ignore[misc]

    def test_fields_match_documented_interface(self):
        rt = QuartoRuntime(
            available=False,
            path=None,
            version=None,
            source="missing",
            message="Not found",
        )
        assert rt.available is False
        assert rt.path is None
        assert rt.version is None
        assert rt.source == "missing"
        assert rt.message == "Not found"

    def test_source_values_are_deterministic(self):
        """Only known source values appear: explicit, managed, system, missing."""
        valid_sources = {"explicit", "managed", "system", "missing"}

        # missing
        with mock.patch("shutil.which", return_value=None):
            with mock.patch.object(Path, "is_file", return_value=False):
                result = find_quarto_runtime(None)
        assert result.source in valid_sources

        # explicit
        settings = Settings(quarto_bin="/fake/quarto")
        with mock.patch.object(Path, "is_file", return_value=False):
            result = find_quarto_runtime(settings)
        assert result.source in valid_sources

        # system
        with mock.patch("shutil.which", return_value="/usr/bin/quarto"):
            with mock.patch.object(Path, "is_file", return_value=True):
                with mock.patch("subprocess.run") as mock_run:
                    mock_run.return_value.returncode = 0
                    mock_run.return_value.stdout = "1.9.38\n"
                    result = find_quarto_runtime(None)
        assert result.source in valid_sources

    def test_version_strips_trailing_newlines(self):
        """Version output with trailing newlines is cleaned up."""
        with mock.patch(
            "app.agent.quarto_runtime._try_managed_path", return_value=None
        ):
            with mock.patch("shutil.which", return_value="/usr/bin/quarto"):
                with mock.patch.object(Path, "is_file", return_value=True):
                    with mock.patch("subprocess.run") as mock_run:
                        mock_run.return_value.returncode = 0
                        mock_run.return_value.stdout = "1.9.38\n\n"

                        result = find_quarto_runtime(None)

        assert result.version == "1.9.38"
