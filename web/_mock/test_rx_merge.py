"""A REST copy must never move a prescription back to an earlier or sibling final state.

Regression for the "two Active on pump chips" race (S5 display): SSE delivers
v5 superseded, then an older REST list still says v5 active. Runs the real
rank() from web/shared/data.js under Node; skipped when Node is not installed.
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

DATA_JS = Path(__file__).resolve().parents[1] / "shared" / "data.js"
NODE = shutil.which("node")

# (state already held from SSE, state in the REST copy, REST copy replaces it?)
CASES = [
    ("superseded", "active", False),  # the race
    ("rejected", "active", False),
    ("superseded", "rejected", False),
    ("rejected", "superseded", False),
    ("active", "active", False),
    ("sent", "active", True),
    ("sent", "rejected", True),
    ("active", "superseded", True),
    ("proposed", "rejected", True),  # declined
    ("proposed", "sent", True),
    ("active", "sent", False),
]


@pytest.mark.skipif(NODE is None, reason="node not installed")
def test_rest_copy_never_moves_backwards(tmp_path):
    source = DATA_JS.read_text(encoding="utf-8")
    pure = re.search(r"const RANK = .*?\nfunction rank\(s\) \{.*?\n\}", source, re.S)
    assert pure, "RANK and rank() not found in data.js"
    harness = tmp_path / "merge.mjs"
    harness.write_text(
        pure.group(0)
        + f"\nconst cases = {json.dumps(CASES)};\n"
        + "console.log(JSON.stringify(cases.map(([have, rest]) => rank(rest) > rank(have))));\n",
        encoding="utf-8",
    )
    out = subprocess.run([NODE, str(harness)], capture_output=True, text=True, check=True)
    assert json.loads(out.stdout) == [want for _, _, want in CASES]
