"""Readable serial output for PlatformIO; incoming telemetry and commands stay intact."""

import os
import sys
from pathlib import Path

from platformio.compat import load_python_module
from platformio.device.monitor.filters.base import DeviceMonitorFilterBase

bench = load_python_module(
    "pump_view_bench", str(Path(__file__).resolve().parents[1] / "tools" / "bench.py")
)


class PumpView(DeviceMonitorFilterBase):
    NAME = "pump_view"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._buffer = ""
        self.color = sys.stdout.isatty() and "NO_COLOR" not in os.environ

    def highlight(self, text, color):
        return f"\033[1;{color}m{text}\033[0m" if self.color else text

    def status(self, value):
        bench.validate_status(value)
        state = value["state"].upper()
        alarm = value["alarm"]
        color = 31 if alarm or state == "ALARM" else {
            "RUNNING": 32, "PAUSED": 33, "PRIMING": 33
        }.get(state, 36)
        seconds = int(value["uptime_ms"] / 1000)
        uptime = f"{seconds // 3600:02}:{seconds // 60 % 60:02}:{seconds % 60:02}"
        delivered, target = value["delivered_ml"], value["target_ml"]
        progress = min(delivered / target, 1) if target > 0 else 0
        filled = int(progress * 24)
        tip = ">" if 0 < progress < 1 else ""
        bar = "=" * filled + tip + "-" * (24 - filled - len(tip))
        lines = [
            "",
            self.highlight(
                f"SIMULATED DELIVERY | {value['pump_id']} | v{value['prescription_version']}"
                f" | {uptime}", 36
            ),
            f"{self.highlight(state, color):s}  |  Rate {value['rate_ml_hr']:.1f} mL/hr",
            f"[{bar}] {progress * 100:5.1f}%  |  {delivered:.2f} / {target:.2f} mL",
        ]
        if alarm:
            lines.append(self.highlight(f"ALARM: {alarm.upper()} -- delivery stopped", 31))
        if value["pending_version"] is not None:
            lines.append(self.highlight(
                f"PENDING: v{value['pending_version']} -- waiting to apply while idle", 33
            ))
        if value.get("last_rejected_version") is not None:
            lines.append(self.highlight(
                f"LAST REJECTION: v{value['last_rejected_version']}"
                f" -- {value.get('last_reject_reason')}", 31
            ))
        if not value["prescription_version"]:
            lines.append("No accepted prescription loaded.")
        return "\n".join(lines) + "\n"

    def event(self, value):
        # Unknown/non-simulated events remain visible in their original form.
        if value["simulated"] is not True:
            return None
        kind = value["type"]
        color = 36
        if kind == "state_changed":
            text = f"STATE: {value['from_state'].upper()} -> {value['to_state'].upper()}"
        elif kind == "alarm_raised":
            text = f"ALARM: {value['alarm'].upper()} -- delivery stopped"
            color = 31
        elif kind == "alarm_cleared":
            text = f"ALARM CLEARED: {value['alarm'].upper()} -- paused; use resume to continue"
            color = 33
        elif kind in {"prescription_applied", "prescription_queued", "prescription_rejected"}:
            label = kind.removeprefix("prescription_").upper()
            text = f"{label}: prescription v{value['version']}"
            if kind == "prescription_queued":
                text += " -- waiting for idle"
                color = 33
            elif kind == "prescription_rejected":
                text += f" -- {value['reason']}"
                color = 31
        else:
            return None
        return self.highlight(f"[SIMULATED] {text}", color) + "\n"

    def line(self, raw):
        parsed = bench.parse_line(raw)
        try:
            if parsed and parsed[0] == "status":
                return self.status(parsed[1])
            if parsed and parsed[0] == "event":
                rendered = self.event(parsed[1])
                if rendered is not None:
                    return rendered
        except (bench.BenchError, KeyError, TypeError, ValueError, OverflowError, AttributeError):
            pass  # Keep malformed/unrecognized messages visible for diagnosis.
        return raw + "\n"

    def rx(self, text):
        self._buffer += text
        output = []
        while "\n" in self._buffer:
            raw, _, self._buffer = self._buffer.partition("\n")
            output.append(self.line(raw.rstrip("\r")))
        if len(self._buffer) > 8192:
            output.append(self._buffer)
            self._buffer = ""
        return "".join(output)
