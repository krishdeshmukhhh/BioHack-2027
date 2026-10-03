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


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.name)
def test_example_validates(path):
    schema_name = path.name.split(".")[0]
    validator = Draft202012Validator(load_schema(schema_name))
    errors = [e.message for e in validator.iter_errors(json.loads(path.read_text()))]
    assert not errors, errors


def test_rejected_event_needs_reason():
    validator = Draft202012Validator(load_schema("event"))
    bad = {
        "pump_id": "pump-001",
        "uptime_ms": 1,
        "type": "prescription_rejected",
        "version": 2,
        "simulated": True,
    }
    assert list(validator.iter_errors(bad))


def test_prescription_needs_confirmation():
    validator = Draft202012Validator(load_schema("prescription"))
    example = json.loads((HERE / "examples" / "prescription.json").read_text())
    del example["confirmed_by"]
    assert list(validator.iter_errors(example))
