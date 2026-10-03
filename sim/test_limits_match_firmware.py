"""The simulator's limits must equal the firmware's limits (S1, and sim parity)."""

import re
from pathlib import Path

from sim import pump_sim

LIMITS_H = Path(__file__).parent.parent / "firmware" / "include" / "limits.h"


def firmware_limits() -> dict[str, float]:
    pattern = re.compile(r"constexpr float (LIMIT_\w+) = ([0-9.]+)f;")
    return {name: float(value) for name, value in pattern.findall(LIMITS_H.read_text())}


def test_limits_match():
    fw = firmware_limits()
    assert len(fw) == 4, fw
    for name, value in fw.items():
        assert getattr(pump_sim, name) == value, name
