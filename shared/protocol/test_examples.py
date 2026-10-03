"""Every example message must validate against its schema.

Example files are named `<schema>.<anything>.json` or `<schema>.json`,
for example `status.running.json` validates against `status.schema.json`.
"""

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

HERE = Path(__file__).parent
EXAMPLES = sorted((HERE / "examples").glob("*.json"))


def load_schema(name: str) -> dict:
    return json.loads((HERE / f"{name}.schema.json").read_text())


def test_there_are_examples():
    assert EXAMPLES, "no example messages found"


@pytest.mark.parametrize("schema_name", ["prescription", "status", "event"])
def test_schema_is_valid(schema_name):
    Draft202012Validator.check_schema(load_schema(schema_name))


def validator_for(name: str) -> Draft202012Validator:
    # Formats such as date-time are only checked with a format checker (PRD R4).
    return Draft202012Validator(
        load_schema(name), format_checker=Draft202012Validator.FORMAT_CHECKER
    )


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.name)
def test_example_validates(path):
    schema_name = path.name.split(".")[0]
    validator = validator_for(schema_name)
    errors = [e.message for e in validator.iter_errors(json.loads(path.read_text()))]
    assert not errors, errors


def test_format_checker_rejects_bad_timestamp():
    example = json.loads((HERE / "examples" / "prescription.json").read_text())
    example["confirmed_at"] = "yesterday"
    assert list(validator_for("prescription").iter_errors(example))


def test_status_reject_fields_are_optional_and_checked():
    status = json.loads((HERE / "examples" / "status.running.json").read_text())
    assert not list(validator_for("status").iter_errors(status))
    status["last_rejected_version"] = 9
    status["last_reject_reason"] = "too_fast"
    assert list(validator_for("status").iter_errors(status))


# Firmware MQTT buffer, set with mqtt.setBufferSize() before connect (PRD R2).
FIRMWARE_MQTT_BUFFER_BYTES = 1024


def test_largest_prescription_fits_firmware_buffer():
    example = json.loads((HERE / "examples" / "prescription.json").read_text())
    example["pump_id"] = "pump-" + "9" * 27
    example["version"] = 2**31 - 1
    example["proposed_by"] = example["confirmed_by"] = "x" * 32
    example["note"] = "é" * 200  # 2 bytes each in UTF-8
    assert not list(validator_for("prescription").iter_errors(example))
    payload = json.dumps(example, separators=(",", ":"), ensure_ascii=False).encode()
    topic = f"pump/{example['pump_id']}/prescription".encode()
    header = 5 + 2 + 2  # fixed header (max), topic length, packet id
    assert len(payload) + len(topic) + header <= FIRMWARE_MQTT_BUFFER_BYTES


def test_rejected_event_needs_reason():
    validator = validator_for("event")
    bad = {
        "pump_id": "pump-001",
        "uptime_ms": 1,
        "type": "prescription_rejected",
        "version": 2,
        "simulated": True,
    }
    assert list(validator.iter_errors(bad))


def test_prescription_needs_confirmation():
    validator = validator_for("prescription")
    example = json.loads((HERE / "examples" / "prescription.json").read_text())
    del example["confirmed_by"]
    assert list(validator.iter_errors(example))
