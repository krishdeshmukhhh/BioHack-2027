"""Voice answers must never confirm a change the caregiver refused (S2).

Runs the real voiceVerdict() from web/shared/speech.js under Node. speech.js
needs a browser to import, so the test slices out the pure functions. Skipped
when Node is not installed (it is not needed on the Pi).
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

SPEECH_JS = Path(__file__).resolve().parents[1] / "shared" / "speech.js"
NODE = shutil.which("node")

EN = (["yes", "confirm"], ["no", "decline"])
ES = (["sí", "si", "confirmar"], ["no", "rechazar"])
CASES = [
    (["yes"], EN, "confirm"),
    (["Yes."], EN, "confirm"),
    (["no"], EN, "decline"),
    (["don't confirm"], EN, None),
    (["yes no"], EN, None),
    (["yes please"], EN, None),
    (["yes", "no"], EN, None),
    (["confirmed"], EN, None),
    ([], EN, None),
    (["Sí"], ES, "confirm"),
    (["si"], ES, "confirm"),
    (["sin cambios"], ES, None),
    (["así"], ES, None),
    (["siga"], ES, None),
    (["sí", "no"], ES, None),
]


@pytest.mark.skipif(NODE is None, reason="node not installed")
def test_voice_verdict_only_acts_on_an_exact_answer(tmp_path):
    source = SPEECH_JS.read_text()
    pure = source[source.index("const normalise") :]
    harness = tmp_path / "verdict.mjs"
    harness.write_text(
        pure
        + f"\nconst cases = {json.dumps(CASES)};\n"
        + "console.log(JSON.stringify(cases.map(([a, [y, n]]) => voiceVerdict(a, y, n))));\n"
    )
    out = subprocess.run([NODE, str(harness)], capture_output=True, text=True, check=True)
    got = json.loads(out.stdout)
    assert got == [want for _, _, want in CASES]
