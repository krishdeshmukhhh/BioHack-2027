"""Scripted rehearsal scenarios for the SIMULATED pump. Prototype demo only.

A scenario is a short declarative list of timed steps. Each step drives the
same ``PumpCore`` / ``MqttLink`` methods the keyboard uses (start, pause/resume,
raise_alarm, clear_alarm, wifi drop/restore), so a scenario can only do what a
person at the pump could do. Nothing here touches limits, confirmation, or how
prescriptions are applied.

Timing: each step waits ``after_s`` from the previous step. By default that is
SIM seconds, so ``--speed`` compresses it, like delivery. Steps marked
``real=True`` wait real seconds instead: these are the moments people have to
watch (an alarm on screen, the hub noticing the pump went offline), which must
not shrink to nothing at ``--speed 600``.

The runner is ticked from the main loop, and the keyboard stays live.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

ACTIONS = (
    "start", "pause_resume", "occlusion", "bag_empty", "clear",
    "drop_wifi", "restore_wifi", "wait_for",
)


class NoPrescriptionError(RuntimeError):
    """A scenario needs a prescription already applied on the pump."""


@dataclass(frozen=True)
class Step:
    after_s: float
    action: str
    arg: str | None = None  # wait_for: the pump state to wait for
    real: bool = False  # True: after_s is real seconds, not scaled by --speed
    label: str = ""

    def __post_init__(self) -> None:
        if self.action not in ACTIONS:
            raise ValueError(f"unknown scenario action {self.action}")
        if self.after_s < 0:
            raise ValueError("after_s must not be negative")


@dataclass(frozen=True)
class Scenario:
    name: str
    summary: str
    suggested_speed: float
    steps: tuple[Step, ...]


# Demo timings only, not clinical guidance. The 3 s real lead-in lets the pump
# connect and publish a status before the feed starts.
_LEAD_IN = Step(3, "start", real=True, label="caregiver starts the feed")


def _fault_and_clear(alarm: str, run_s: float) -> tuple[Step, ...]:
    return (
        Step(run_s, alarm, label=f"{alarm.replace('_', ' ')} detected"),
        Step(10, "clear", real=True, label="caregiver clears the alarm, pump goes to paused"),
        Step(3, "pause_resume", real=True, label="caregiver resumes the feed"),
    )


SCENARIOS: dict[str, Scenario] = {
    s.name: s
    for s in (
        Scenario(
            "occlusion",
            "DEMO steps 6-8: start a feed, occlusion, caregiver clears it, feed resumes",
            60,
            (_LEAD_IN, *_fault_and_clear("occlusion", 600)),
        ),
        Scenario(
            "bag_empty",
            "Start a feed, bag empty alarm, caregiver clears it, feed resumes",
            60,
            (_LEAD_IN, *_fault_and_clear("bag_empty", 600)),
        ),
        Scenario(
            "wifi_drop",
            "S6: start a feed, MQTT drops for 30 real s mid-feed (hub shows offline "
            "after the Last Will), feed keeps going, delivered jumps on reconnect",
            60,
            (
                _LEAD_IN,
                Step(300, "drop_wifi", label="wifi lost (no DISCONNECT, Last Will fires)"),
                Step(30, "restore_wifi", real=True, label="wifi back, reconnecting"),
            ),
        ),
        Scenario(
            "overnight",
            "Compressed overnight feed: two occlusions, each cleared and resumed, "
            "then runs to complete",
            600,
            (
                _LEAD_IN,
                *_fault_and_clear("occlusion", 2 * 3600),
                *_fault_and_clear("occlusion", 3 * 3600),
                Step(0, "wait_for", arg="complete", label="feed complete"),
            ),
        ),
    )
}


def describe() -> str:
    lines = ["Scenarios (combine with --demo-seed or --state-file):"]
    for s in SCENARIOS.values():
        lines.append(f"  {s.name:<10} {s.summary}. Suggested --speed {s.suggested_speed:g}")
    return "\n".join(lines)


class ScenarioRunner:
    """Fires a scenario's steps from the main loop. Uses the pump's clock."""

    def __init__(
        self,
        scenario: Scenario,
        core: Any,
        link: Any = None,
        clock: Callable[[], float] | None = None,
        out: Callable[[str], None] = print,
    ) -> None:
        if core.prescription is None:
            raise NoPrescriptionError(
                f"scenario '{scenario.name}' needs a prescription already on the pump. "
                "Add --demo-seed (v7 at 60 mL/hr, idle) or --state-file with a saved one."
            )
        self.scenario = scenario
        self.core = core
        self.link = link
        self.clock = clock or core._clock
        self.out = out
        self.speed = core.speed
        self._start = self.clock()
        self._base = self._start  # when the previous step was due
        self._index = 0
        self.fired: list[tuple[float, str, bool]] = []  # (sim t, action, took effect)
        self.out(f"[scenario] {scenario.name}: {scenario.summary}")

    @property
    def done(self) -> bool:
        return self._index >= len(self.scenario.steps)

    def sim_elapsed(self) -> float:
        return (self.clock() - self._start) * self.speed

    def tick(self) -> None:
        while not self.done:
            step = self.scenario.steps[self._index]
            due = self._base + (step.after_s if step.real else step.after_s / self.speed)
            now = self.clock()
            if now < due:
                return
            if step.action == "wait_for":
                if self.core.state != step.arg:
                    return
                due = now  # the next step counts from when the state was reached
            self._base = due
            self._index += 1
            self._fire(step)
            if self.done:
                self.out(f"[scenario] {self.scenario.name} done; keys still work (q to quit)")

    def _fire(self, step: Step) -> None:
        ok = self._do(step)
        t = self.sim_elapsed()
        self.fired.append((t, step.action, ok))
        name = step.arg if step.action == "wait_for" else step.action
        msg = f"[scenario] t={t:.0f}s {name}"
        if step.label:
            msg += f" ({step.label})"
        if not ok:
            msg += f" -- ignored, pump state is {self.core.state}"
        self.out(msg)

    def _do(self, step: Step) -> bool:
        a, core, link = step.action, self.core, self.link
        if a == "start":
            return core.start()
        if a == "pause_resume":
            return core.toggle_pause()
        if a in ("occlusion", "bag_empty"):
            return core.raise_alarm(a)
        if a == "clear":
            return core.clear_alarm()
        if a == "drop_wifi":
            if link is None or link.dropped:
                return False
            link.drop()
            return True
        if a == "restore_wifi":
            if link is None or not link.dropped:
                return False
            link.restore()
            return True
        return True  # wait_for: the condition was checked in tick()
