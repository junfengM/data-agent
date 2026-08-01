"""Local-controlled Python execution for analysis steps.

Execution mode is controlled by generated_code_execution:

- "disabled" (default, safe): generated code does not execute. Returns a
  blocked result explaining that execution must be enabled.

- "local-dev" (development only): code runs in a local subprocess using
  sys.executable with a scrubbed environment and run-directory output
  collection. This is NOT a security boundary — do not enable for
  untrusted users, shared servers, or production.

- "sandbox" (future): isolated sandbox execution. Currently a placeholder
  that returns a clear error when no sandbox backend is configured.

The legacy mode "local" is accepted as an alias for "local-dev" for
backward compatibility with existing configurations.

Set DATA_AGENT_GENERATED_CODE_EXECUTION=local-dev in server/.env to enable
local development execution.
"""
from __future__ import annotations

import ast
import importlib
import json
import keyword
import os
import shutil
import subprocess
import sys
import sysconfig
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.core.settings import get_settings


def safe_growth_rate(current: float, previous: float | None) -> float | None:
    if previous is None or previous == 0:
        return None
    return (current - previous) / previous


def format_growth_rate(value: float | None, current: float | None = None, previous: float | None = None) -> str:
    if value is None:
        if previous is not None and previous == 0 and current is not None and current > 0:
            return "新出现"
        return "N/A"
    return f"{value:.1%}"


_GROWTH_RATE_HELPERS = """
def safe_growth_rate(current, previous):
    if previous is None or previous == 0:
        return None
    return (current - previous) / previous

def format_growth_rate(value, current=None, previous=None):
    if value is None:
        if previous is not None and previous == 0 and current is not None and current > 0:
            return "新出现"
        return "N/A"
    return f"{value:.1%}"
"""


@dataclass(frozen=True)
class ExecutionResult:
    returncode: int
    stdout: str
    stderr: str
    tables: list[dict]
    charts: list[dict]
    generated_files: list[Path]


@dataclass(frozen=True)
class AnalysisDependencyStatus:
    package: str
    available: bool
    version: str | None = None
    error: str | None = None


# Keep only non-secret process settings. HOME is rewritten to the run directory
# so generated code cannot discover the user's real home path through env vars.
SAFE_ENV_KEYS = frozenset({"PATH", "TMPDIR", "LANG", "LC_ALL"})
OUTPUT_EXTENSIONS = {".csv", ".json", ".png", ".jpg", ".jpeg", ".svg", ".html"}

# Keep generated analysis code on the dependency set we actually ship/support.
# Standard library imports are also allowed via _is_stdlib_module, except for
# modules that can open network/process escape hatches in local-dev mode.
ALLOWED_THIRD_PARTY_IMPORTS = frozenset({
    "duckdb",
    "numpy",
    "openpyxl",
    "pandas",
    "plotly",
    "xlsxwriter",
    "yaml",
})


def get_analysis_dependency_status() -> list[AnalysisDependencyStatus]:
    """Detect which allowed third-party packages are actually importable."""
    results: list[AnalysisDependencyStatus] = []
    for package in sorted(ALLOWED_THIRD_PARTY_IMPORTS):
        try:
            module = importlib.import_module(package)
            version = getattr(module, "__version__", None)
            results.append(AnalysisDependencyStatus(
                package=package,
                available=True,
                version=str(version) if version else None,
            ))
        except Exception as exc:
            results.append(AnalysisDependencyStatus(
                package=package,
                available=False,
                error=f"{type(exc).__name__}: {exc}",
            ))
    return results


def get_available_analysis_imports() -> frozenset[str]:
    """Return the subset of ALLOWED_THIRD_PARTY_IMPORTS actually importable."""
    statuses = get_analysis_dependency_status()
    return frozenset(s.package for s in statuses if s.available)


def format_analysis_dependency_status_for_prompt() -> str:
    """Format dependency availability as a prompt section for the planner."""
    statuses = get_analysis_dependency_status()
    available = [s for s in statuses if s.available]
    unavailable = [s for s in statuses if not s.available]

    lines = [
        "## Runtime Python dependency availability",
        "",
        "Available third-party packages:",
    ]
    for s in available:
        ver = f" ({s.version})" if s.version else ""
        lines.append(f"- {s.package}{ver}")

    if unavailable:
        lines.append("")
        lines.append("Unavailable packages:")
        for s in unavailable:
            lines.append(f"- {s.package}: {s.error}")

    lines.append("")
    lines.append("Rules:")
    lines.append("- Generated analysis code may import only packages listed as available.")
    lines.append("- Do not import unavailable packages even if they appear in the broader supported list.")
    if any(s.package == "plotly" and s.available for s in available):
        lines.append("- Prefer plotly for HTML charts when plotly is available.")
        lines.append(
            "- Do not use matplotlib, seaborn, pandas.DataFrame.plot, or static PNG chart generation "
            "for report charts. Use plotly HTML charts for Web Report deliverables."
        )
    lines.append("- Do not call pip/install commands at runtime.")

    return "\n".join(lines)
BLOCKED_STDLIB_IMPORTS = frozenset({
    "http",
    "ftplib",
    "smtplib",
    "socket",
    "ssl",
    "subprocess",
    "urllib",
})
BLOCKED_RUNTIME_CALLS = frozenset({
    "os.system",
    "os.popen",
    "os.spawnl",
    "os.spawnle",
    "os.spawnlp",
    "os.spawnlpe",
    "os.spawnv",
    "os.spawnve",
    "os.spawnvp",
    "os.spawnvpe",
})


class CodeRunner(Protocol):
    """Runner interface for executing generated analysis code.

    Each runner receives a prepared script and a run directory and returns
    a CompletedProcess with captured output. The caller handles script
    preparation and output classification.
    """

    def run(
        self,
        script_path: Path,
        run_dir: Path,
        timeout_seconds: int | None,
    ) -> subprocess.CompletedProcess: ...


class LocalDevRunner:
    """Execute code in a local subprocess using sys.executable.

    This runner scrubs the environment and rewrites HOME, but it is NOT a
    security sandbox. Generated code runs on the host with no filesystem
    or network isolation. Use only in development with trusted code.
    """

    def run(
        self,
        script_path: Path,
        run_dir: Path,
        timeout_seconds: int | None,
    ) -> subprocess.CompletedProcess:
        try:
            return subprocess.run(
                [sys.executable, str(script_path)],
                cwd=run_dir,
                env=_scrubbed_env(run_dir),
                text=True,
                capture_output=True,
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            return subprocess.CompletedProcess(
                args=exc.cmd or [sys.executable, str(script_path)],
                returncode=124,
                stdout=(exc.stdout or "") if isinstance(exc.stdout, str) else "",
                stderr=(
                    ((exc.stderr or "") if isinstance(exc.stderr, str) else "")
                    + f"\nAnalysis step timed out after {timeout_seconds} seconds."
                ).strip(),
            )


class SandboxRunner:
    """Placeholder for sandbox execution.

    This runner always fails because no sandbox backend is configured.
    To enable sandbox execution, deploy a real backend and implement
    the run() method with container/VM isolation.
    """

    def run(
        self,
        script_path: Path,
        run_dir: Path,
        timeout_seconds: int | None,
    ) -> subprocess.CompletedProcess:
        return subprocess.CompletedProcess(
            args=[],
            returncode=2,
            stdout="",
            stderr=(
                "Sandbox execution is configured but no sandbox backend is available. "
                "Set DATA_AGENT_GENERATED_CODE_EXECUTION=local-dev for development "
                "or implement a sandbox backend."
            ),
        )


def run_analysis_code(
    code: str,
    run_dir: Path,
    dataset_paths: list[Path],
    *,
    timeout_seconds: int | None = None,
    generated_code_execution: str = "disabled",
) -> ExecutionResult:
    """Execute analysis code with access to copied dataset files.

    generated_code_execution controls the execution mode:
    - "disabled": code does not run; returns a blocked result.
    - "local-dev" (or "local"): code runs in a local subprocess.
    - "sandbox": placeholder that returns a clear error.

    "local" is accepted as a backward-compatible alias for "local-dev".
    Local execution is bounded by analysis_execution_timeout_seconds unless the
    caller explicitly passes timeout_seconds=None to disable the timeout.
    """
    mode = _normalize_mode(generated_code_execution)
    if timeout_seconds is None:
        timeout_seconds = get_settings().analysis_execution_timeout_seconds

    if mode == "disabled":
        return ExecutionResult(
            returncode=2,
            stdout="",
            stderr=(
                "Generated code execution is disabled. "
                "Set DATA_AGENT_GENERATED_CODE_EXECUTION=local-dev in server/.env "
                "to enable local development execution."
            ),
            tables=[],
            charts=[],
            generated_files=[],
        )

    if mode == "sandbox":
        return ExecutionResult(
            returncode=2,
            stdout="",
            stderr=(
                "Sandbox execution is configured but no sandbox backend is available. "
                "Set DATA_AGENT_GENERATED_CODE_EXECUTION=local-dev for development "
                "or implement a sandbox backend."
            ),
            tables=[],
            charts=[],
            generated_files=[],
        )

    import_error = _validate_imports(code)
    if import_error:
        return ExecutionResult(
            returncode=2,
            stdout="",
            stderr=import_error,
            tables=[],
            charts=[],
            generated_files=[],
        )

    # local-dev mode
    runner = LocalDevRunner()
    run_dir.mkdir(parents=True, exist_ok=True)
    datasets_dir = run_dir / "datasets"
    datasets_dir.mkdir(exist_ok=True)

    container_dataset_paths: list[Path] = []
    for src in dataset_paths:
        dst = datasets_dir / src.name
        if not dst.exists():
            shutil.copy2(src, dst)
        container_dataset_paths.append(dst)

    dataset_var_lines = _build_dataset_vars(container_dataset_paths)
    files_before = _collect_output_candidates(run_dir)

    wrapped_code = _wrap_code(code, dataset_var_lines, run_dir)
    script_path = run_dir / "_analysis_step.py"
    script_path.write_text(wrapped_code, encoding="utf-8")

    result = runner.run(script_path, run_dir, timeout_seconds)

    # Persist stdout/stderr alongside the script for post-run debugging.
    if result.stdout:
        (run_dir / "_stdout.txt").write_text(result.stdout, encoding="utf-8")
    if result.stderr:
        (run_dir / "_stderr.txt").write_text(result.stderr, encoding="utf-8")

    files_after = _collect_output_candidates(run_dir)
    new_files = files_after - files_before - {script_path.resolve()}
    tables, charts, others = _classify_outputs(new_files)

    stderr = result.stderr.strip()
    if "ModuleNotFoundError" in stderr or "ImportError" in stderr:
        stderr = _friendly_import_runtime_error(stderr)

    return ExecutionResult(
        returncode=result.returncode,
        stdout=result.stdout.strip(),
        stderr=stderr,
        tables=tables,
        charts=charts,
        generated_files=[f for f in others if f.suffix != ".py"],
    )


def _normalize_mode(raw: str) -> str:
    """Normalize execution mode string.

    Accepts "local" as a backward-compatible alias for "local-dev".
    Returns one of: "disabled", "local-dev", "sandbox".
    """
    if raw in ("local", "local-dev"):
        return "local-dev"
    if raw in ("disabled", "sandbox"):
        return raw
    return "disabled"


# ── helpers ────────────────────────────────────────────────────────────

def _validate_imports(code: str) -> str | None:
    """Return a user-facing error when generated code uses unsupported APIs."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        # Let Python produce the full syntax traceback during execution.
        return None

    available_imports = get_available_analysis_imports()
    blocked_imports: list[str] = []
    unavailable_imports: list[str] = []
    unsupported_imports: list[str] = []
    blocked_calls: list[str] = []

    for node in ast.walk(tree):
        modules: list[str] = []
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules = [node.module]

        for module in modules:
            root = module.split(".", 1)[0]
            if root.startswith("_"):
                continue
            if root in BLOCKED_STDLIB_IMPORTS:
                blocked_imports.append(root)
                continue
            if root in ALLOWED_THIRD_PARTY_IMPORTS:
                if root not in available_imports:
                    unavailable_imports.append(root)
                continue
            if _is_stdlib_module(root):
                continue
            unsupported_imports.append(root)

        if isinstance(node, ast.Call):
            call_name = _call_name(node.func)
            if call_name in BLOCKED_RUNTIME_CALLS:
                blocked_calls.append(call_name)

    if blocked_imports or blocked_calls:
        blocked = sorted(set(blocked_imports + blocked_calls))
        return (
            "Blocked risky API in generated analysis code: "
            f"{', '.join(blocked)}. Generated analysis steps may transform local "
            "datasets and write artifacts, but they must not spawn subprocesses "
            "or open network connections in local-dev mode."
        )

    if unavailable_imports:
        unavailable_text = ", ".join(sorted(set(unavailable_imports)))
        available_text = ", ".join(sorted(available_imports))
        return (
            "Unavailable import in current analysis runtime: "
            f"{unavailable_text}. "
            f"Available analysis packages: {available_text}. "
            "Rewrite without unavailable packages; do not install packages at runtime."
        )

    if unsupported_imports:
        blocked_text = ", ".join(sorted(set(unsupported_imports)))
        allowed_text = ", ".join(sorted(ALLOWED_THIRD_PARTY_IMPORTS))
        return (
            "Unsupported import in generated analysis code: "
            f"{blocked_text}. Use only the supported analysis packages "
            f"({allowed_text}) plus safe Python standard library modules. "
            "Rewrite the step using pandas, numpy, duckdb, or plotly; "
            "do not install packages at runtime."
        )

    return None


def _call_name(func: ast.AST) -> str | None:
    if isinstance(func, ast.Attribute):
        parent = _call_name(func.value)
        return f"{parent}.{func.attr}" if parent else func.attr
    if isinstance(func, ast.Name):
        return func.id
    return None


def _is_stdlib_module(root: str) -> bool:
    if root in sys.builtin_module_names:
        return True
    stdlib_path = sysconfig.get_paths().get("stdlib")
    if not stdlib_path:
        return False
    module_path = Path(stdlib_path) / f"{root}.py"
    package_path = Path(stdlib_path) / root
    return module_path.exists() or package_path.exists()


def _friendly_import_runtime_error(stderr: str) -> str:
    return (
        stderr
        + "\n\nDependency guidance: generated analysis code should not rely on packages "
        "outside the server's supported analysis environment. Rewrite with pandas, "
        "numpy, duckdb, plotly, openpyxl, yaml, or safe Python standard library modules. "
        "Do not call pip/install commands at runtime."
    )


def _scrubbed_env(run_dir: Path) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k in SAFE_ENV_KEYS}
    home_dir = run_dir / "_home"
    home_dir.mkdir(parents=True, exist_ok=True)
    env["HOME"] = str(home_dir)
    env["PYTHONNOUSERSITE"] = "1"
    env.pop("PYTHONPATH", None)
    return env


def _collect_output_candidates(run_dir: Path) -> set[Path]:
    """Collect user-visible output files recursively.

    Excludes copied inputs, the rewritten HOME directory, caches, hidden files,
    symlinks, files outside the run directory after resolution, and oversized
    outputs. This keeps generated artifact discovery bounded even in unsafe
    local execution mode.
    """
    resolved_run_dir = run_dir.resolve()
    ignored_roots = {resolved_run_dir / "datasets", resolved_run_dir / "_home"}
    candidates: set[Path] = set()

    for path in sorted(run_dir.rglob("*")):
        if len(candidates) >= get_settings().analysis_max_output_files:
            break
        try:
            if path.is_symlink() or not path.is_file():
                continue
            resolved_path = path.resolve()
            if not resolved_path.is_relative_to(resolved_run_dir):
                continue
            if path.name.startswith(".") or path.name == "_analysis_step.py":
                continue
            under_ignored_root = any(
                resolved_path == root or root in resolved_path.parents
                for root in ignored_roots
            )
            if under_ignored_root:
                continue
            if "__pycache__" in path.parts:
                continue
            if path.suffix.lower() not in OUTPUT_EXTENSIONS:
                continue
            if resolved_path.stat().st_size > get_settings().analysis_max_output_bytes:
                continue
        except OSError:
            continue
        candidates.add(resolved_path)

    return candidates


def _build_dataset_vars(paths: list[Path]) -> list[str]:
    """Build Python variable assignments for dataset paths."""
    lines: list[str] = []
    used: set[str] = set()
    for idx, path in enumerate(paths):
        name = _safe_var_name(path, idx)
        base_name = name
        dedupe_idx = 1
        while name in used:
            name = f"{base_name}_{dedupe_idx}"
            dedupe_idx += 1
        used.add(name)
        lines.append(f'{name} = {str(path)!r}')
    return lines


def _wrap_code(code: str, dataset_vars: list[str], run_dir: Path) -> str:
    """Wrap user code with imports and working directory setup."""
    cwd = str(run_dir)
    dataset_assignments = _parse_dataset_assignments(dataset_vars)
    dataset_path_values = [path for _, path in dataset_assignments]
    dataset_var_names = [name for name, _ in dataset_assignments]
    dataset_var_map = {name: path for name, path in dataset_assignments}
    return (
        "import sys, json, os\n"
        "import pandas as pd\n"
        "import duckdb\n"
        f"os.chdir({cwd!r})\n"
        + "\n".join(dataset_vars) + "\n"
        f"dataset_paths = {dataset_path_values!r}\n"
        f"dataset_path_variables = {dataset_var_names!r}\n"
        f"dataset_vars = {dataset_var_map!r}\n"
        + _GROWTH_RATE_HELPERS + "\n"
        + code + "\n"
    )


def _parse_dataset_assignments(dataset_vars: list[str]) -> list[tuple[str, str]]:
    assignments: list[tuple[str, str]] = []
    for line in dataset_vars:
        name, value = line.split(" = ", 1)
        path_value = ast.literal_eval(value)
        assignments.append((name, str(path_value)))
    return assignments


def _classify_outputs(new_files: set[Path]) -> tuple[list[dict], list[dict], list[Path]]:
    tables: list[dict] = []
    charts: list[dict] = []
    others: list[Path] = []

    for f in sorted(new_files):
        suffix = f.suffix.lower()
        if suffix == ".csv":
            try:
                import pandas as pd
                df = pd.read_csv(f)
                tables.append({
                    "name": f.stem,
                    "path": str(f),
                    "rows": len(df),
                    "columns": list(df.columns),
                    "preview": _preview_df(df),
                })
            except Exception:
                others.append(f)
        elif suffix in {".png", ".jpg", ".jpeg", ".svg", ".html"}:
            charts.append({
                "name": f.stem,
                "path": str(f),
                "type": suffix.lstrip("."),
                "render_mode": "file",
                "asset_path": str(f),
            })
        elif suffix == ".json":
            try:
                data = json.loads(f.read_text())
                if _looks_like_plotly_json(data):
                    charts.append({
                        "name": f.stem,
                        "path": str(f),
                        "type": "plotly",
                        "render_mode": "file",
                        "asset_path": str(f),
                    })
                else:
                    tables.append({
                        "name": f.stem,
                        "path": str(f),
                        "rows": len(data) if isinstance(data, list) else 1,
                        "columns": list(data[0].keys()) if isinstance(data, list) and data else [],
                        "preview": data[:5] if isinstance(data, list) else [data],
                    })
            except Exception:
                others.append(f)
        else:
            others.append(f)

    return tables, charts, others


def _looks_like_plotly_json(data: Any) -> bool:
    """Distinguish Plotly figure JSON from plain business data JSON.

    Plotly figures have a "data" key whose value is a list of traces, each
    containing "type", "x", or "y". Plain business JSON like
    {"data": [{"month": "2026-01", "revenue": 123}]} should be classified
    as a table, not a chart.
    """
    if not isinstance(data, dict):
        return False
    traces = data.get("data")
    if not isinstance(traces, list) or not traces:
        return False
    has_trace_keys = any(
        isinstance(t, dict) and ("type" in t or "x" in t or "y" in t)
        for t in traces
    )
    if not has_trace_keys:
        return False
    has_layout_or_typed_trace = (
        "layout" in data
        or any(isinstance(t, dict) and "type" in t for t in traces)
    )
    return has_layout_or_typed_trace


def _preview_df(df, max_rows: int = 10) -> list[dict]:
    return df.head(max_rows).fillna("").to_dict(orient="records")


def _safe_var_name(path: Path, index: int) -> str:
    name = path.stem.replace("-", "_").replace(".", "_").replace(" ", "_")
    name = "".join(c for c in name if c.isalnum() or c == "_")
    name = name.strip("_") or f"dataset_{index}"
    if not name.isidentifier() or keyword.iskeyword(name):
        name = f"dataset_{name}"
    return name
