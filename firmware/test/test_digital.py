"""Validate actual C++ digital telemetry against the shared contract."""

import importlib.util
import json
import re
import subprocess
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT.parent
BINARY = ROOT / ".pio/build/native/program"
spec = importlib.util.spec_from_file_location("firmware_demo", ROOT / "tools/demo.py")
demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo)


def run(commands: list[dict], store: Path | None = None) -> tuple[list[dict], str]:
    args = [str(BINARY)] + ([str(store)] if store else [])
    result = subprocess.run(
        args,
        input="".join(json.dumps(command) + "\n" for command in commands),
        text=True,
        capture_output=True,
        check=True,
    )
    return [json.loads(line) for line in result.stdout.splitlines()], result.stderr


def validate(messages: list[dict]) -> None:
    for message in messages:
        kind = message["topic"].split("/")[-1]
        if kind == "availability":
            assert message["payload"] in ("online", "offline")
            continue
        schema = json.loads((PROJECT / f"shared/protocol/{kind}.schema.json").read_text())
        Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER).validate(
            message["payload"]
        )
        assert message["payload"]["simulated"] is True


def test_demo_wire_messages_and_remote_change_loop():
    messages, errors = run(demo.demo_commands())
    assert not errors
    validate(messages)
    payloads = [m["payload"] for m in messages if isinstance(m["payload"], dict)]
    events = [p for p in payloads if "type" in p]
    assert [p["version"] for p in events if p["type"] == "prescription_applied"] == [7, 8]
    assert any(p.get("reason") == "rate_out_of_range" and p["version"] == 9 for p in events)
    assert any(p["type"] == "prescription_queued" and p["version"] == 8 for p in events)
    statuses = [p for p in payloads if "state" in p]
    running = next(p for p in statuses if p["delivered_ml"] > 0)
    assert running["prescription_version"] == 7
    assert running["delivered_ml"] == pytest.approx(1)
    paused = next(p for p in statuses if p["state"] == "paused")
    alarmed = [p for p in statuses if p["state"] == "alarm"]
    assert paused["delivered_ml"] == alarmed[0]["delivered_ml"] == alarmed[-1]["delivered_ml"]
    assert statuses[-1]["state"] == "idle"
    assert statuses[-1]["prescription_version"] == 8
    assert statuses[-1]["rate_ml_hr"] == 90


def test_durable_restart_retained_replay_and_older_rejection(tmp_path):
    prescription = demo.demo_commands()[0]["payload"]
    store = tmp_path / "current.json"
    first, errors = run([{"command": "prescription", "payload": prescription}], store)
    assert not errors
    validate(first)
    older = dict(prescription, version=6)
    restarted, errors = run(
        [
            {"command": "prescription", "payload": prescription},
            {"command": "prescription", "payload": older},
        ],
        store,
    )
    assert not errors
    validate(restarted)
    statuses = [m["payload"] for m in restarted if m["topic"].endswith("/status")]
    assert statuses[0]["state"] == "idle"
    assert statuses[0]["prescription_version"] == 7
    assert all(p["prescription_version"] == 7 for p in statuses)
    events = [m["payload"] for m in restarted if m["topic"].endswith("/event")]
    assert len(events) == 1
    assert events[0]["reason"] == "stale_version"
    assert events[0]["version"] == 6


def test_two_hundred_character_note_fits_configured_mqtt_packet():
    prescription = demo.demo_commands()[4]["payload"]
    payload = json.dumps(prescription, separators=(",", ":")).encode()
    topic = b"pump/pump-001/prescription"
    # Fixed header, remaining-length bytes, topic-length prefix, QoS1 packet id.
    capacity = int(re.search(r"MQTT_BUFFER_SIZE = (\d+)",
                            (ROOT / "include/config.h").read_text())[1])
    assert len(payload) + len(topic) + 2 + 2 + 5 <= capacity
    messages, errors = run([{"command": "prescription", "payload": prescription}])
    assert not errors
    validate(messages)
    assert any(
        m["payload"].get("type") == "prescription_applied"
        for m in messages if isinstance(m["payload"], dict)
    )


def test_two_hundred_unicode_characters_fit_and_apply():
    prescription = dict(demo.demo_commands()[4]["payload"], note="😀" * 200)
    payload = json.dumps(prescription, separators=(",", ":"), ensure_ascii=False).encode()
    capacity = int(re.search(r"MQTT_BUFFER_SIZE = (\d+)",
                            (ROOT / "include/config.h").read_text())[1])
    assert len(payload) + len(b"pump/pump-001/prescription") + 9 <= capacity
    messages, errors = run([{"command": "prescription", "payload": prescription}])
    assert not errors
    validate(messages)
    assert any(
        m["payload"].get("type") == "prescription_applied"
        for m in messages if isinstance(m["payload"], dict)
    )


def test_offline_serial_demo_starts_and_fault_clear_requires_separate_resume():
    messages, errors = run([
        {"command": "demo"},
        {"command": "start"},
        {"command": "tick", "elapsed_ms": 1000},
        {"command": "tick", "elapsed_ms": 60000},
        {"command": "occlusion"},
        {"command": "clear"},
        {"command": "tick", "elapsed_ms": 60000},
        {"command": "resume"},
        {"command": "tick", "elapsed_ms": 60000},
    ])
    assert not errors
    validate(messages)
    statuses = [m["payload"] for m in messages if m["topic"].endswith("/status")]
    assert statuses[1]["prescription_version"] == 1
    assert statuses[1]["rate_ml_hr"] == 60
    assert statuses[1]["target_ml"] == 5
    alarm = next(p for p in statuses if p["state"] == "alarm")
    assert alarm["rate_ml_hr"] == 0
    paused = [p for p in statuses if p["state"] == "paused"]
    assert all(p["delivered_ml"] == pytest.approx(1) for p in paused)
    assert statuses[-1]["state"] == "running"
    assert statuses[-1]["delivered_ml"] == pytest.approx(2)


def test_pending_replay_never_sets_rejection_recovery_fields():
    commands = demo.demo_commands()[:5]
    commands.append(commands[4])
    commands.append({"command": "stop"})
    messages, errors = run(commands)
    assert not errors
    validate(messages)
    statuses = [m["payload"] for m in messages if m["topic"].endswith("/status")]
    assert statuses[-2]["pending_version"] == 8
    assert statuses[-1]["prescription_version"] == 8
    assert all(p["last_rejected_version"] is None for p in statuses)
    assert not any(
        m["payload"].get("type") == "prescription_rejected"
        for m in messages if isinstance(m["payload"], dict)
    )


def test_versioned_rejection_repeats_in_status_for_lost_event_recovery():
    messages, errors = run([
        demo.demo_commands()[0],
        demo.demo_commands()[5],
        {"command": "tick", "elapsed_ms": 2000},
        {"command": "status"},
    ])
    assert not errors
    validate(messages)
    statuses = [m["payload"] for m in messages if m["topic"].endswith("/status")]
    assert all(p["last_rejected_version"] == 9 for p in statuses[-3:])
    assert all(p["last_reject_reason"] == "rate_out_of_range" for p in statuses[-3:])


@pytest.mark.parametrize("bad", ["broken-json", "{}", "null"])
def test_unversioned_malformed_input_never_claims_rejection_of_a_real_version(bad):
    messages, errors = run([{"command": "prescription", "payload": bad}])
    validate(messages)
    assert "unversioned malformed" in errors
    assert not any(m["topic"].endswith("/event") for m in messages)
    assert all(
        m["payload"]["prescription_version"] == 0
        for m in messages if m["topic"].endswith("/status")
    )
