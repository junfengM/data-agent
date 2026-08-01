"""Async execution runner tests: cancellation, timeout, and resource limits."""
import asyncio
import os
import time

import pytest

from app.core.settings import get_settings
from app.tools.execution import (
    LocalDevRunnerAsync,
    run_analysis_code,
    run_analysis_code_async,
)


@pytest.fixture
def run_dir(tmp_path):
    return tmp_path / "run"


@pytest.mark.anyio
async def test_async_execution_matches_sync_result(run_dir):
    code = "import pandas as pd; df = pd.DataFrame({'a':[1,2]}); print(df['a'].sum())"
    sync_result = run_analysis_code(
        code=code,
        run_dir=run_dir,
        dataset_paths=[],
        generated_code_execution="local-dev",
    )
    async_result = await run_analysis_code_async(
        code=code,
        run_dir=run_dir,
        dataset_paths=[],
        generated_code_execution="local-dev",
    )
    assert async_result.returncode == sync_result.returncode == 0
    assert async_result.stdout.strip() == sync_result.stdout.strip()


@pytest.mark.anyio
async def test_async_execution_timeout_kills_subprocess(run_dir):
    code = "import time; time.sleep(30)"
    start = time.monotonic()
    result = await run_analysis_code_async(
        code=code,
        run_dir=run_dir,
        dataset_paths=[],
        generated_code_execution="local-dev",
        timeout_seconds=1,
    )
    elapsed = time.monotonic() - start
    assert result.returncode == 124
    assert "timed out" in result.stderr
    assert elapsed < 20, f"subprocess was not killed promptly: {elapsed:.1f}s"


@pytest.mark.anyio
async def test_async_execution_cancellation_kills_subprocess(run_dir):
    code = "import time; time.sleep(30)"
    task = asyncio.create_task(
        run_analysis_code_async(
            code=code,
            run_dir=run_dir,
            dataset_paths=[],
            generated_code_execution="local-dev",
        )
    )
    await asyncio.sleep(1)
    start = time.monotonic()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    elapsed = time.monotonic() - start
    assert elapsed < 20, f"cancelled subprocess was not killed promptly: {elapsed:.1f}s"


@pytest.mark.skipif(not hasattr(os, "fork"), reason="POSIX resource limits only")
@pytest.mark.anyio
async def test_async_execution_applies_fsize_rlimit(run_dir, monkeypatch):
    limit = 1024 * 1024
    monkeypatch.setattr(get_settings(), "analysis_max_output_bytes", limit)
    run_dir.mkdir(parents=True, exist_ok=True)
    script = run_dir / "probe.py"
    script.write_text(
        "import resource; print(resource.getrlimit(resource.RLIMIT_FSIZE)[0])",
        encoding="utf-8",
    )
    result = await LocalDevRunnerAsync().run(script, run_dir, timeout_seconds=30)
    assert result.returncode == 0, result.stderr
    assert str(limit) in result.stdout
