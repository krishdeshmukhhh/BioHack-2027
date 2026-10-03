"""Tests for the fictional history generator (S8: everything labelled simulated)."""

import json
import re
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from sim import generate_history as gh

ROOT = Path(__file__).parent.parent
LIMITS_H = ROOT / "firmware" / "include" / "limits.h"
EVENT_SCHEMA = ROOT / "shared" / "protocol" / "event.schema.json"
END = date(2026, 10, 3)


def firmware_limits() -> dict[str, float]:
    pattern = re.compile(r"constexpr float (LIMIT_\w+) = ([0-9.]+)f;")
    return {name: float(value) for name, value in pattern.findall(LIMITS_H.read_text())}


def run(tmp_path: Path, *args: str) -> dict:
    out = tmp_path / "nested" / "history.json"
    gh.main(["--end-date", END.isoformat(), "--out", str(out), *args])
    return json.loads(out.read_text())


@pytest.fixture
def history(tmp_path):
    return run(tmp_path)


def parse_ts(ts: str) -> datetime:
    assert ts.endswith("Z"), ts
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")


def test_deterministic_for_seed(tmp_path):
    a = run(tmp_path / "a", "--seed", "7")
    b = run(tmp_path / "b", "--seed", "7")
    c = run(tmp_path / "c", "--seed", "8")
    assert a == b
    assert a != c
    assert a["seed"] == 7


def test_output_path_respected_and_summary(tmp_path, capsys):
    out = tmp_path / "deep" / "dir" / "custom.json"
    gh.main(["--end-date", "2026-01-31", "--out", str(out)])
    assert out.exists()
    assert "simulated" in capsys.readouterr().out.lower()


@pytest.mark.parametrize("days", [30, 10])
def test_shape_three_patients_by_n_days(tmp_path, days):
    h = run(tmp_path, "--days", str(days))
    assert set(h) == {"simulated", "seed", "generated_for_end_date", "patients", "daily", "alarms"}
    assert h["generated_for_end_date"] == END.isoformat()
    ids = [p["id"] for p in h["patients"]]
    assert ids == ["pat-01", "pat-02", "pat-03"]
    assert [p["pump_id"] for p in h["patients"]] == ["pump-001", "pump-002", "pump-003"]
    assert {p["pattern"] for p in h["patients"]} == {
        "on_target", "drifting_under_target", "night_occlusions"}
    assert len(h["daily"]) == 3 * days
    expected_dates = [(END - timedelta(days=days - 1 - i)).isoformat() for i in range(days)]
    for pid in ids:
        assert [r["date"] for r in h["daily"] if r["patient_id"] == pid] == expected_dates
    assert h["daily"] == sorted(h["daily"], key=lambda r: (r["patient_id"], r["date"]))
    for r in h["daily"]:
        assert set(r) == {"patient_id", "pump_id", "date", "delivered_ml", "prescribed_ml",
                          "alarm_count", "simulated"}
    for a in h["alarms"]:
        assert set(a) == {"patient_id", "pump_id", "alarm", "raised_at", "cleared_at", "simulated"}


def test_every_record_simulated(history):
    assert history["simulated"] is True
    for key in ("patients", "daily", "alarms"):
        assert history[key], key
        assert all(r["simulated"] is True for r in history[key]), key


def test_names_are_obviously_fictional(history):
    assert all(p["display_name"].startswith("Demo ") for p in history["patients"])


def test_alarm_codes_and_timestamps(history):
    codes = set(json.loads(EVENT_SCHEMA.read_text())["properties"]["alarm"]["enum"])
    first = END - timedelta(days=29)
    pump_of = {p["id"]: p["pump_id"] for p in history["patients"]}
    for a in history["alarms"]:
        assert a["alarm"] in codes
        raised, cleared = parse_ts(a["raised_at"]), parse_ts(a["cleared_at"])
        assert cleared > raised
        assert first <= raised.date() <= END
        assert a["pump_id"] == pump_of[a["patient_id"]]


def test_alarm_count_matches_alarms(history):
    counts = Counter((a["patient_id"], a["raised_at"][:10]) for a in history["alarms"])
    for r in history["daily"]:
        assert r["alarm_count"] == counts.get((r["patient_id"], r["date"]), 0)
    assert sum(r["alarm_count"] for r in history["daily"]) == len(history["alarms"])


def test_values_within_firmware_limits(history):
    fw = firmware_limits()
    lo, hi = fw["LIMIT_VOLUME_MIN_ML"], fw["LIMIT_VOLUME_MAX_ML"]
    for r in history["daily"]:
        assert lo <= r["prescribed_ml"] <= hi
        assert lo <= r["delivered_ml"] <= r["prescribed_ml"]
    assert gh.VOLUME_MIN_ML == lo and gh.VOLUME_MAX_ML == hi


def rows(history, pattern):
    pid = next(p["id"] for p in history["patients"] if p["pattern"] == pattern)
    return pid, [r for r in history["daily"] if r["patient_id"] == pid]


@pytest.mark.parametrize("seed", ["2026", "1", "99"])
def test_on_target_and_drifting(tmp_path, seed):
    h = run(tmp_path, "--seed", seed)
    _, on_target = rows(h, "on_target")
    assert all(r["delivered_ml"] >= 0.95 * r["prescribed_ml"] for r in on_target)

    _, drifting = rows(h, "drifting_under_target")
    assert all(r["delivered_ml"] < 0.9 * r["prescribed_ml"] for r in drifting[-3:])
    assert drifting[0]["delivered_ml"] >= 0.95 * drifting[0]["prescribed_ml"]


@pytest.mark.parametrize("seed", ["2026", "1", "99"])
def test_night_occlusions_on_most_nights(tmp_path, seed):
    h = run(tmp_path, "--seed", seed)
    pid, _ = rows(h, "night_occlusions")
    per_night = Counter()
    for a in h["alarms"]:
        if a["patient_id"] != pid:
            continue
        assert a["alarm"] == "occlusion"
        raised, cleared = parse_ts(a["raised_at"]), parse_ts(a["cleared_at"])
        for t in (raised, cleared):
            assert t.hour >= 22 or t.hour < 6, a
        per_night[(raised + timedelta(hours=2)).date()] += 1  # 22:00 belongs to the next morning
    nights_with_several = sum(1 for n in per_night.values() if n >= 2)
    assert nights_with_several >= 0.75 * 30

    # The other patients have no night occlusions.
    others = [a for a in h["alarms"] if a["patient_id"] != pid]
    assert all(a["alarm"] != "occlusion" for a in others)
