"""Run web regressions with Node's built-in module sandbox; no npm dependencies."""

import shutil
import subprocess
from pathlib import Path

import pytest

NODE = shutil.which("node")


@pytest.mark.skipif(NODE is None, reason="node not installed")
def test_sync4_web_regressions():
    result = subprocess.run(
        [NODE, "--experimental-vm-modules", str(Path(__file__).with_name("sync4_checks.mjs"))],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
