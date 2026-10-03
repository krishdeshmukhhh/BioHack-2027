"""Validate MQTT payloads against the schemas in shared/protocol/ (the contract)."""

import json
from functools import cache
from pathlib import Path

from jsonschema import Draft202012Validator

PROTOCOL_DIR = Path(__file__).resolve().parents[2] / "shared" / "protocol"


@cache
def validator(schema_name: str) -> Draft202012Validator:
    schema = json.loads((PROTOCOL_DIR / f"{schema_name}.schema.json").read_text())
    # R4: formats such as date-time are only checked with an explicit format checker.
    return Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)


def errors(schema_name: str, message: object) -> list[str]:
    """Return a list of validation errors; empty means valid."""
    return [e.message for e in validator(schema_name).iter_errors(message)]
