"""SIMULATED software pump. Prototype and demo only, not a medical device.

Must be indistinguishable from the ESP32 firmware on MQTT: same topics, same
schemas, same state machine, same validation order and rejection reasons, and
the same limits as firmware/include/limits.h. Everything it sends carries
"simulated": true.

Layout:

- ``PumpCore``: pure state machine, prescription validation, delivery and
  alarms. No MQTT. Takes an injected ``publish(topic, payload)`` callback and an
  injected ``clock()`` returning seconds, so it is unit-testable without a broker.
- ``MqttLink``: thin paho-mqtt 2.x wrapper (Last Will, availability, subscribe in
  on_connect, simulated wifi drop, graceful offline on exit).
- ``main()``: CLI, keyboard fault injection, scripted scenarios
  (``sim/scenarios.py``), main tick loop.

Run with ``python -m sim.pump_sim`` (or ``make sim``).
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import signal
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sim.scenarios import SCENARIOS, NoPrescriptionError, ScenarioRunner, describe

# Keep in step with firmware/include/limits.h. Demo values, not clinical guidance.
LIMIT_RATE_MIN_ML_HR = 1.0
LIMIT_RATE_MAX_ML_HR = 150.0
LIMIT_VOLUME_MIN_ML = 1.0
LIMIT_VOLUME_MAX_ML = 1000.0

# Mirrors STATUS_INTERVAL_MS in firmware/include/config.h. Real time, never scaled.
STATUS_INTERVAL_S = 2.0
# Simulated seconds spent priming before running, and showing "complete" before idle.
PRIME_S = 3.0
COMPLETE_HOLD_S = 5.0
# MQTT keepalive in seconds (the broker fires the Last Will after 1.5 x this).
KEEPALIVE_S = 15

STATES = ("idle", "priming", "running", "paused", "alarm", "complete")
ALARMS = ("occlusion", "bag_empty", "low_battery", "sensor_mismatch")
MODES = ("continuous", "bolus")

# Allowed transitions, exactly as docs/research/ARCHITECTURE-DIAGRAMS.md section 7.
TRANSITIONS = {
    ("idle", "priming"),
    ("priming", "running"),
    ("running", "paused"),
    ("paused", "running"),
    ("running", "complete"),
    ("complete", "idle"),
    ("running", "alarm"),
    ("paused", "alarm"),
    ("alarm", "paused"),
}

log = logging.getLogger("pump_sim")

PublishFn = Callable[[str, str], None]
ClockFn = Callable[[], float]


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: Any) -> bool:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:  # an integer too large for a float is malformed
        return False


# --demo-feed starting state, from docs/DEMO.md. Demo values only.
DEMO_SEED = {
    "version": 7,
    "mode": "continuous",
    "rate_ml_hr": 60,
    "volume_ml": 500,
    "proposed_by": "clin-01",
    "proposed_at": "2026-10-03T07:55:00Z",
    "confirmed_by": "care-01",
    "confirmed_at": "2026-10-03T08:00:00Z",
}

VERSION_MAX = 2**31 - 1  # check 1 bound in docs/PROTOCOL.md (int32 on the ESP32)


def _is_version(value: Any) -> bool:
    return _is_int(value) and 1 <= value <= VERSION_MAX


def _non_empty_str(value: Any) -> bool:
    return isinstance(value, str) and value != ""


def _reject_constant(name: str) -> Any:
    # NaN and Infinity are not JSON. Treat them as a parse failure.
    raise ValueError(f"invalid JSON constant {name}")


# Keys allowed in a prescription (shared/protocol/prescription.schema.json).
PRESCRIPTION_KEYS = frozenset({
    "pump_id", "version", "mode", "rate_ml_hr", "volume_ml", "proposed_by",
    "proposed_at", "confirmed_by", "confirmed_at", "note",
})
NOTE_MAX_CHARS = 200


def _date_time(value: Any) -> bool:
    from jsonschema import Draft202012Validator

    return isinstance(value, str) and Draft202012Validator.FORMAT_CHECKER.conforms(
        value, "date-time"
    )


def is_well_formed(rx: Any) -> bool:
    """Check 1 of docs/PROTOCOL.md: the prescription schema shape, except that
    confirmation may be missing or empty (check 3) and the rate and volume
    range is left to checks 5 and 6. Same as the firmware's parsePrescription."""
    if not isinstance(rx, dict) or not set(rx) <= PRESCRIPTION_KEYS:
        return False
    if not all(_non_empty_str(rx.get(k)) for k in ("pump_id", "mode", "proposed_by")):
        return False
    if not all(k not in rx or isinstance(rx[k], str) for k in (
        "confirmed_by", "confirmed_at", "note",
    )):
        return False
    return (
        _is_version(rx.get("version"))
        and rx["mode"] in MODES
        and _date_time(rx.get("proposed_at"))
        and (not rx.get("confirmed_at") or _date_time(rx["confirmed_at"]))
        and len(rx.get("note", "")) <= NOTE_MAX_CHARS
        and _is_number(rx.get("rate_ml_hr"))
        and _is_number(rx.get("volume_ml"))
    )


class PumpCore:
    """The simulated pump, without any networking. Thread-safe via one lock."""

    def __init__(
        self,
        pump_id: str,
        publish: PublishFn,
        clock: ClockFn = time.monotonic,
        speed: float = 1.0,
        state_file: Path | None = None,
    ) -> None:
        if speed <= 0:
            raise ValueError("speed must be positive")
        self.pump_id = pump_id
        self._publish = publish
        self._clock = clock
        self.speed = speed
        self.state_file = state_file
        self._lock = threading.RLock()

        self._boot = clock()
        self._last_tick = self._boot
        self._last_status: float | None = None
        self._state_entered = self._boot

        self.state = "idle"
        self.alarm: str | None = None
        self.prescription: dict[str, Any] | None = None
        self.pending: dict[str, Any] | None = None
        self.delivered_ml = 0.0
        self.last_rejected_version: int | None = None
        self.last_reject_reason: str | None = None
        self._load_state()

    # ---- topics and payloads -------------------------------------------

    @property
    def topic_status(self) -> str:
        return f"pump/{self.pump_id}/status"

    @property
    def topic_event(self) -> str:
        return f"pump/{self.pump_id}/event"

    def uptime_ms(self) -> int:
        return max(0, int((self._clock() - self._boot) * 1000))

    @property
    def version(self) -> int:
        return int(self.prescription["version"]) if self.prescription else 0

    @property
    def pending_version(self) -> int | None:
        return int(self.pending["version"]) if self.pending else None

    def _event(self, type_: str, **fields: Any) -> None:
        payload = {"pump_id": self.pump_id, "uptime_ms": self.uptime_ms(), "type": type_}
        payload.update(fields)
        payload["simulated"] = True
        self._publish(self.topic_event, json.dumps(payload))

    def status(self) -> dict[str, Any]:
        with self._lock:
            rx = self.prescription
            # Rate the pump is set to; 0 while an alarm has the actuator stopped.
            rate = 0 if (rx is None or self.state == "alarm") else rx["rate_ml_hr"]
            uptime_s = self._clock() - self._boot
            return {
                "pump_id": self.pump_id,
                "uptime_ms": self.uptime_ms(),
                "state": self.state,
                "rate_ml_hr": rate,
                "delivered_ml": round(self.delivered_ml, 2),
                "target_ml": rx["volume_ml"] if rx else 0,
                "alarm": self.alarm,
                "prescription_version": self.version,
                "pending_version": self.pending_version,
                "battery_pct": max(20, 100 - int(uptime_s // 300)),
                "last_rejected_version": self.last_rejected_version,
                "last_reject_reason": self.last_reject_reason,
                "simulated": True,
            }

    def publish_status(self) -> None:
        with self._lock:
            self._publish(self.topic_status, json.dumps(self.status()))
            self._last_status = self._clock()

    # ---- state machine -------------------------------------------------

    def transition_to(self, new_state: str) -> None:
        """The only place the state changes. Logs and publishes state_changed."""
        with self._lock:
            old = self.state
            if (old, new_state) not in TRANSITIONS:
                raise ValueError(f"illegal transition {old} -> {new_state}")
            self.state = new_state
            self._state_entered = self._clock()
            log.info("state %s -> %s", old, new_state)
            self._event("state_changed", from_state=old, to_state=new_state)
            if new_state == "idle" and self.pending is not None:
                # S4: a queued prescription is applied on the next return to idle.
                rx, self.pending = self.pending, None
                self._apply(rx)

    def _apply(self, rx: dict[str, Any]) -> None:
        self.prescription = rx
        self._save_state()
        log.info(
            "applied v%s: %s mL/hr, %s mL (demo values)",
            rx["version"], rx["rate_ml_hr"], rx["volume_ml"],
        )
        self._event("prescription_applied", version=rx["version"])

    # ---- prescriptions -------------------------------------------------

    def _reject(self, version: int, reason: str) -> None:
        self.last_rejected_version = version
        self.last_reject_reason = reason
        log.warning("rejected v%s: %s", version, reason)
        self._event("prescription_rejected", version=version, reason=reason)

    def handle_prescription(self, payload: bytes | str) -> str:
        """Validate and apply, queue, ignore or reject one message, in the
        docs/PROTOCOL.md order. Returns the outcome: applied, queued, ignored
        (replay), dropped (malformed with no readable version), or the reason.
        """
        with self._lock:
            duplicate_keys = False

            def prescription_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
                nonlocal duplicate_keys
                rx: dict[str, Any] = {}
                duplicate_version = False
                for key, value in pairs:
                    if key in rx:
                        duplicate_keys = True
                        duplicate_version |= key == "version"
                    rx[key] = value
                # An ambiguous version cannot identify a rejection event.
                if duplicate_version:
                    del rx["version"]
                return rx

            try:
                rx = json.loads(payload, parse_constant=_reject_constant,
                                object_pairs_hook=prescription_object)
            except (ValueError, UnicodeDecodeError):
                rx = None

            # 1. shape (fixed field list)
            if duplicate_keys or not is_well_formed(rx):
                version = rx.get("version") if isinstance(rx, dict) else None
                if _is_version(version):
                    self._reject(version, "malformed")
                    return "malformed"
                log.warning("dropped malformed prescription with no readable version")
                return "dropped"
            version = rx["version"]

            # 2. pump id
            if rx["pump_id"] != self.pump_id:
                self._reject(version, "wrong_pump")
                return "wrong_pump"

            # 3. caregiver confirmation (S2)
            if not (
                _non_empty_str(rx.get("confirmed_by"))
                and _non_empty_str(rx.get("confirmed_at"))
            ):
                self._reject(version, "not_confirmed")
                return "not_confirmed"

            # 4. version (S3). Equal to current or pending is a retained replay.
            if version == self.version or version == self.pending_version:
                log.debug("ignored replay of v%s", version)
                return "ignored"
            if version < self.version or (
                self.pending_version is not None and version < self.pending_version
            ):
                self._reject(version, "stale_version")
                return "stale_version"

            # 5, 6. hard limits (S1). Reject, never clamp.
            if not (LIMIT_RATE_MIN_ML_HR <= rx["rate_ml_hr"] <= LIMIT_RATE_MAX_ML_HR):
                self._reject(version, "rate_out_of_range")
                return "rate_out_of_range"
            if not (LIMIT_VOLUME_MIN_ML <= rx["volume_ml"] <= LIMIT_VOLUME_MAX_ML):
                self._reject(version, "volume_out_of_range")
                return "volume_out_of_range"

            accepted = dict(rx)  # fully validated; kept whole so a reload passes check 1
            if self.state == "idle":
                self._apply(accepted)
                return "applied"
            # S4: never change mid-feed. A newer pending replaces an older one.
            self.pending = accepted
            log.info("queued v%s until idle (state %s)", version, self.state)
            self._event("prescription_queued", version=version)
            return "queued"

    # ---- caregiver actions and faults ----------------------------------

    def start(self) -> bool:
        with self._lock:
            if self.state != "idle":
                log.info("start ignored: state is %s", self.state)
                return False
            if self.prescription is None:
                log.info("start ignored: no prescription applied yet")
                return False
            self.delivered_ml = 0.0
            self.transition_to("priming")
            return True

    def toggle_pause(self) -> bool:
        with self._lock:
            if self.state == "running":
                self.transition_to("paused")
            elif self.state == "paused":
                self.transition_to("running")
            else:
                log.info("pause/resume ignored: state is %s", self.state)
                return False
            return True

    def raise_alarm(self, alarm: str) -> bool:
        with self._lock:
            if alarm not in ALARMS:
                raise ValueError(alarm)
            if self.state not in ("running", "paused"):
                log.info("alarm %s ignored: state is %s", alarm, self.state)
                return False
            self.alarm = alarm
            self._event("alarm_raised", alarm=alarm)
            self.transition_to("alarm")
            return True

    def clear_alarm(self) -> bool:
        """Caregiver clears at the pump. Goes to paused, never straight to running (FR-16)."""
        with self._lock:
            if self.state != "alarm" or self.alarm is None:
                log.info("clear ignored: no active alarm")
                return False
            alarm, self.alarm = self.alarm, None
            self._event("alarm_cleared", alarm=alarm)
            self.transition_to("paused")
            return True

    # ---- time ----------------------------------------------------------

    def tick(self) -> None:
        """Advance delivery and timers and publish status when due. Knows nothing
        about the network, so it runs the same whether MQTT is up or down (S6)."""
        with self._lock:
            now = self._clock()
            elapsed = max(0.0, now - self._last_tick)
            self._last_tick = now
            in_state_sim_s = (now - self._state_entered) * self.speed

            if self.state == "priming" and in_state_sim_s >= PRIME_S:
                self.transition_to("running")
            elif self.state == "running" and self.prescription is not None:
                target = float(self.prescription["volume_ml"])
                rate = float(self.prescription["rate_ml_hr"])
                self.delivered_ml += rate * (elapsed * self.speed) / 3600.0
                if self.delivered_ml >= target:
                    self.delivered_ml = target
                    self.transition_to("complete")
            elif self.state == "complete" and in_state_sim_s >= COMPLETE_HOLD_S:
                self.transition_to("idle")

            if self._last_status is None or now - self._last_status >= STATUS_INTERVAL_S:
                self.publish_status()

    # ---- persistence (mirrors NVS) -------------------------------------

    def _load_state(self) -> None:
        if not self.state_file or not self.state_file.exists():
            return
        try:
            rx = json.loads(self.state_file.read_text()).get("prescription")
        except (OSError, ValueError, AttributeError):
            log.warning("could not read state file %s, starting empty", self.state_file)
            return
        if rx is not None:
            self._restore(rx, str(self.state_file))

    def _restore(self, rx: Any, source: str) -> bool:
        """Boot-time load, like NVS. Defence in depth: the record must pass
        checks 1, 2, 3, 5 and 6 again. Publishes nothing."""
        if (
            is_well_formed(rx)
            and rx["pump_id"] == self.pump_id
            and _non_empty_str(rx.get("confirmed_by"))
            and _non_empty_str(rx.get("confirmed_at"))
            and LIMIT_RATE_MIN_ML_HR <= rx["rate_ml_hr"] <= LIMIT_RATE_MAX_ML_HR
            and LIMIT_VOLUME_MIN_ML <= rx["volume_ml"] <= LIMIT_VOLUME_MAX_ML
        ):
            self.prescription = rx
            log.info("loaded v%s from %s", rx["version"], source)
            return True
        log.warning("discarded invalid prescription from %s", source)
        return False

    def seed_demo_prescription(self) -> bool:
        """PLAN phase 1: a hard-coded starting prescription, as if loaded from
        NVS, matching the docs/DEMO.md reset state (v7 at 60 mL/hr). Only used
        when nothing was loaded, so it never overrides a real prescription."""
        if self.prescription is not None:
            return False
        return self._restore(dict(DEMO_SEED, pump_id=self.pump_id), "the demo seed")

    def _save_state(self) -> None:
        if not self.state_file:
            return
        try:
            tmp = self.state_file.with_suffix(".tmp")
            tmp.write_text(json.dumps({"prescription": self.prescription}))
            tmp.replace(self.state_file)
        except OSError as exc:
            log.warning("could not write state file: %s", exc)


class MqttLink:
    """Thin paho-mqtt wrapper. Status at QoS 0, events and availability at QoS 1 (topics.md)."""

    def __init__(self, core: PumpCore, host: str, port: int, client: Any = None) -> None:
        self.core = core
        self.host = host
        self.port = port
        self.dropped = False
        self.connected = False
        pid = core.pump_id
        self.topic_availability = f"pump/{pid}/availability"
        self.topic_prescription = f"pump/{pid}/prescription"
        if client is None:
            import paho.mqtt.client as mqtt

            client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"{pid}-sim")
        self.client = client
        client.will_set(self.topic_availability, "offline", qos=1, retain=True)
        client.reconnect_delay_set(min_delay=1, max_delay=5)
        client.on_connect = self.on_connect
        client.on_disconnect = self.on_disconnect
        client.on_message = self.on_message

    def publish(self, topic: str, payload: str) -> None:
        """Core publish callback. Lost while offline, like the ESP32 (topics.md):
        status at QoS 0, events at QoS 1."""
        if self.dropped or not self.connected:
            return
        qos = 0 if topic.endswith("/status") else 1
        self.client.publish(topic, payload, qos=qos, retain=False)

    def on_connect(self, client, userdata, flags, reason_code, properties=None) -> None:
        if getattr(reason_code, "is_failure", False):
            log.warning("MQTT connect failed: %s", reason_code)
            return
        self.connected = True
        log.info("MQTT connected to %s:%s", self.host, self.port)
        client.publish(self.topic_availability, "online", qos=1, retain=True)
        # Subscribe here so it comes back after every reconnect (retained replay).
        client.subscribe(self.topic_prescription, qos=1)

    def on_disconnect(self, client, userdata, flags, reason_code, properties=None) -> None:
        self.connected = False
        log.warning("MQTT disconnected (%s); feed continues (S6)", reason_code)

    def on_message(self, client, userdata, msg) -> None:
        if msg.topic != self.topic_prescription:
            return
        try:
            self.core.handle_prescription(msg.payload)
        except Exception:
            # Never let a bad payload stop paho's network thread.
            log.exception("error handling prescription; message dropped")

    def start(self) -> None:
        """Non-blocking: connects and reconnects in paho's background thread."""
        self.client.connect_async(self.host, self.port, keepalive=KEEPALIVE_S)
        self.client.loop_start()

    def drop(self) -> None:
        """Simulate wifi loss: stop the network loop and kill the socket without a
        DISCONNECT, so the broker fires the Last Will. The core keeps ticking (S6)."""
        if self.dropped:
            return
        self.dropped = True
        self.connected = False
        self.client.loop_stop()
        sock = self.client.socket()
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
        log.warning("wifi DROPPED (simulated). Feed continues (S6).")

    def restore(self) -> None:
        if not self.dropped:
            return
        self.dropped = False
        # The loop thread sees the dead socket and reconnects on its own.
        self.client.loop_start()
        log.info("wifi restored (simulated), reconnecting")

    def toggle_drop(self) -> None:
        if self.dropped:
            self.restore()
        else:
            self.drop()

    def shutdown(self) -> None:
        """Graceful exit (R8): a DISCONNECT discards the Last Will, so publish
        retained offline ourselves first."""
        if self.connected and not self.dropped:
            info = self.client.publish(self.topic_availability, "offline", qos=1, retain=True)
            try:
                info.wait_for_publish(timeout=2)
            except (RuntimeError, ValueError):
                pass
            self.client.disconnect()
        self.client.loop_stop()


HELP = (
    "keys + Enter: s=start feed  p=pause/resume  o=occlusion  b=bag empty  "
    "c=clear alarm  d=drop/restore wifi  i=print status  h=help  q=quit"
)

BANNER = """
==============================================================
  SIMULATED pump  (prototype demo, NOT a medical device)
  pump_id={pump_id}  broker={host}:{port}  speed=x{speed:g}
==============================================================
"""


def handle_key(key: str, core: PumpCore, link: MqttLink | None, stop: threading.Event) -> None:
    key = key.strip().lower()
    if not key:
        return
    k = key[0]
    if k == "s":
        core.start()
    elif k == "p":
        core.toggle_pause()
    elif k == "o":
        core.raise_alarm("occlusion")
    elif k == "b":
        core.raise_alarm("bag_empty")
    elif k == "c":
        core.clear_alarm()
    elif k == "d" and link is not None:
        link.toggle_drop()
    elif k == "i":
        print(json.dumps(core.status()), flush=True)
    elif k == "q":
        stop.set()
    else:
        print(HELP, flush=True)


def _stdin_reader(core: PumpCore, link: MqttLink, stop: threading.Event) -> None:
    for line in sys.stdin:
        handle_key(line, core, link, stop)
        if stop.is_set():
            return


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass
    p = argparse.ArgumentParser(
        prog="python -m sim.pump_sim",
        description="SIMULATED pump for the Smart Pump prototype demo. Not a medical device.",
        epilog=HELP,
    )
    p.add_argument("--pump-id", default=os.environ.get("PUMP_ID", "pump-001"))
    p.add_argument("--host", default=os.environ.get("MQTT_HOST", "localhost"))
    p.add_argument("--port", type=int, default=int(os.environ.get("MQTT_PORT", "1883")))
    p.add_argument(
        "--speed",
        type=float,
        default=float(os.environ.get("SIM_SPEED", "1")),
        help="time-speed factor for delivery, priming and completion; "
        "status stays every 2 s (env SIM_SPEED, default 1)",
    )
    p.add_argument(
        "--state-file",
        type=Path,
        default=os.environ.get("SIM_STATE_FILE") or None,
        help="persist the applied prescription across restarts, like NVS (env SIM_STATE_FILE)",
    )
    seed = p.add_mutually_exclusive_group()
    seed.add_argument(
        "--demo-seed",
        action="store_true",
        help="if no prescription is loaded, start from the DEMO.md reset state: "
        "v7 at 60 mL/hr applied, pump idle",
    )
    seed.add_argument(
        "--demo-feed",
        action="store_true",
        help="if no prescription is loaded, start from the DEMO.md seed (v7 at 60 mL/hr) "
        "and start a feed straight away (PLAN phase 1 check)",
    )
    p.add_argument(
        "--scenario",
        choices=sorted(SCENARIOS),
        help="run a scripted rehearsal scenario (needs a prescription: add --demo-seed "
        "or --state-file); keys stay live",
    )
    p.add_argument(
        "--list-scenarios", action="store_true", help="list scenarios and exit"
    )
    p.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    args = p.parse_args(argv)
    if args.speed <= 0:
        p.error("--speed must be positive")
    return args


def prepare_core(
    args: argparse.Namespace, publish: PublishFn, clock: ClockFn = time.monotonic
) -> PumpCore:
    """Build the core and apply the --demo-seed / --demo-feed starting state."""
    core = PumpCore(
        args.pump_id, publish=publish, clock=clock, speed=args.speed,
        state_file=args.state_file,
    )
    if args.demo_seed or args.demo_feed:
        core.seed_demo_prescription()
    if args.demo_feed:
        core.start()
    return core


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    if args.list_scenarios:
        print(describe())
        return
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s SIM %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    print(
        BANNER.format(pump_id=args.pump_id, host=args.host, port=args.port, speed=args.speed),
        flush=True,
    )
    print(HELP, flush=True)

    link_box: list[MqttLink] = []

    def publish(topic: str, payload: str) -> None:
        if link_box:
            link_box[0].publish(topic, payload)

    core = prepare_core(args, publish)
    link = MqttLink(core, args.host, args.port)
    link_box.append(link)

    runner = None
    if args.scenario:
        try:
            runner = ScenarioRunner(
                SCENARIOS[args.scenario], core, link,
                out=lambda line: print(line, flush=True),
            )
        except NoPrescriptionError as exc:
            print(f"error: {exc}", file=sys.stderr, flush=True)
            sys.exit(2)

    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    threading.Thread(target=_stdin_reader, args=(core, link, stop), daemon=True).start()

    link.start()
    try:
        while not stop.is_set():
            core.tick()
            if runner is not None:
                runner.tick()
            stop.wait(0.1)
    except KeyboardInterrupt:
        pass
    finally:
        log.info("shutting down: publishing offline")
        link.shutdown()


if __name__ == "__main__":
    main()
