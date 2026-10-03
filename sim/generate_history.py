"""Generate fictional feeding history for the clinician dashboard (PLAN phase 4).

Prototype demo data only. All patients are invented, every record carries
"simulated": true, and every number is a demo value, not clinical guidance.

Run: python -m sim.generate_history [--days 30] [--seed 2026] [--end-date YYYY-MM-DD] [--out PATH]

Output is one JSON file (default sim/data/history.json) with this shape, which
the hub loads:

    {"simulated": true, "seed": int, "generated_for_end_date": "YYYY-MM-DD",
     "patients": [{"id", "display_name", "pump_id", "pattern", "simulated"}],
     "daily":    [{"patient_id", "pump_id", "date", "delivered_ml",
                   "prescribed_ml", "alarm_count", "simulated"}],
     "alarms":   [{"patient_id", "pump_id", "alarm", "raised_at",
                   "cleared_at", "simulated"}]}
"""

from __future__ import annotations

import argparse
import json
import random
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

DEFAULT_SEED = 2026
DEFAULT_DAYS = 30
DEFAULT_OUT = Path(__file__).parent / "data" / "history.json"

# Must stay within firmware/include/limits.h (LIMIT_VOLUME_MIN_ML..LIMIT_VOLUME_MAX_ML).
VOLUME_MIN_ML = 1.0
VOLUME_MAX_ML = 1000.0

PATTERN_ON_TARGET = "on_target"
PATTERN_DRIFTING_UNDER = "drifting_under_target"
PATTERN_NIGHT_OCCLUSIONS = "night_occlusions"

# Invented names and arbitrary demo volumes.
PATIENTS = [
    {"id": "pat-01", "display_name": "Demo Child Aster", "pump_id": "pump-001",
     "pattern": PATTERN_ON_TARGET, "prescribed_ml": 900.0},
    {"id": "pat-02", "display_name": "Demo Child Bramble", "pump_id": "pump-002",
     "pattern": PATTERN_DRIFTING_UNDER, "prescribed_ml": 750.0},
    {"id": "pat-03", "display_name": "Demo Child Cobalt", "pump_id": "pump-003",
     "pattern": PATTERN_NIGHT_OCCLUSIONS, "prescribed_ml": 600.0},
]

# The drifting pattern ends near this fraction of the prescribed volume...
DRIFT_FINAL_FRACTION = 0.70
# ...and is held below UNDER_TARGET_FRACTION for at least its last DRIFT_UNDER_DAYS days.
DRIFT_UNDER_DAYS = 5
UNDER_TARGET_FRACTION = 0.90

# Night window used for the occlusion pattern: 22:00 to 06:00 UTC.
NIGHT_START = time(22, 0)
NIGHT_HOURS = 8


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _alarm(patient: dict, code: str, raised: datetime, minutes: int) -> dict:
    return {
        "patient_id": patient["id"],
        "pump_id": patient["pump_id"],
        "alarm": code,
        "raised_at": _iso(raised),
        "cleared_at": _iso(raised + timedelta(minutes=minutes)),
        "simulated": True,
    }


def _night_alarms(rng: random.Random, patient: dict, day: date, first_day: date) -> list[dict]:
    """Occlusions in the night that ends on the morning of `day` (22:00 the day before to 06:00)."""
    if day == first_day:
        # Do not reach back before the generated range: use only the post-midnight part.
        start = datetime.combine(day, time(0, 0), tzinfo=UTC)
        window_min = (NIGHT_HOURS - 2) * 60
    else:
        start = datetime.combine(day - timedelta(days=1), NIGHT_START, tzinfo=UTC)
        window_min = NIGHT_HOURS * 60
    # Most nights have several occlusions; an occasional quiet night keeps it believable.
    count = 0 if rng.random() < 0.1 else rng.randint(2, 4)
    alarms = []
    for _ in range(count):
        raised = start + timedelta(minutes=rng.randint(0, window_min - 30))  # clears before 06:00
        alarms.append(_alarm(patient, "occlusion", raised, rng.randint(3, 20)))
    return alarms


def _day_alarms(rng: random.Random, patient: dict, day: date) -> list[dict]:
    """Rare daytime alarms for the quieter patterns."""
    if rng.random() >= 0.12:
        return []
    code = rng.choice(["bag_empty", "low_battery"])
    at = time(rng.randint(8, 19), rng.randint(0, 59))
    raised = datetime.combine(day, at, tzinfo=UTC)
    return [_alarm(patient, code, raised, rng.randint(2, 10))]


def _delivered_fraction(
    rng: random.Random, pattern: str, index: int, days: int, night_alarms: int
) -> float:
    if pattern == PATTERN_ON_TARGET:
        return rng.uniform(0.96, 1.0)
    if pattern == PATTERN_DRIFTING_UNDER:
        progress = index / max(days - 1, 1)
        fraction = 1.0 - (1.0 - DRIFT_FINAL_FRACTION) * progress + rng.uniform(-0.02, 0.02)
        if index >= days - DRIFT_UNDER_DAYS:
            fraction = min(fraction, UNDER_TARGET_FRACTION - 0.03)
        return min(fraction, 1.0)
    # Night occlusions: each stoppage costs a little volume.
    return max(0.6, rng.uniform(0.97, 1.0) - 0.03 * night_alarms)


def generate(
    days: int = DEFAULT_DAYS, seed: int = DEFAULT_SEED, end_date: date | None = None
) -> dict:
    """Build the history dict. Deterministic for a given (days, seed, end_date)."""
    if days < 1:
        raise ValueError("days must be at least 1")
    end = end_date or datetime.now(UTC).date()
    first_day = end - timedelta(days=days - 1)
    rng = random.Random(seed)

    patients_out: list[dict] = []
    daily: list[dict] = []
    alarms: list[dict] = []

    for patient in PATIENTS:
        prescribed = patient["prescribed_ml"]
        if not VOLUME_MIN_ML <= prescribed <= VOLUME_MAX_ML:
            raise ValueError(f"{patient['id']} prescribed_ml outside limits.h")
        patients_out.append({
            "id": patient["id"],
            "display_name": patient["display_name"],
            "pump_id": patient["pump_id"],
            "pattern": patient["pattern"],
            "simulated": True,
        })

        patient_alarms: list[dict] = []
        night_counts: list[int] = []
        for i in range(days):
            day = first_day + timedelta(days=i)
            if patient["pattern"] == PATTERN_NIGHT_OCCLUSIONS:
                night = _night_alarms(rng, patient, day, first_day)
                night_counts.append(len(night))
                patient_alarms.extend(night)
            else:
                night_counts.append(0)
                patient_alarms.extend(_day_alarms(rng, patient, day))

        # alarm_count is by the UTC calendar date of raised_at.
        per_date: dict[str, int] = {}
        for a in patient_alarms:
            per_date[a["raised_at"][:10]] = per_date.get(a["raised_at"][:10], 0) + 1

        for i in range(days):
            day = first_day + timedelta(days=i)
            fraction = _delivered_fraction(rng, patient["pattern"], i, days, night_counts[i])
            delivered = round(min(max(prescribed * fraction, VOLUME_MIN_ML), prescribed), 1)
            daily.append({
                "patient_id": patient["id"],
                "pump_id": patient["pump_id"],
                "date": day.isoformat(),
                "delivered_ml": delivered,
                "prescribed_ml": prescribed,
                "alarm_count": per_date.get(day.isoformat(), 0),
                "simulated": True,
            })
        alarms.extend(patient_alarms)

    daily.sort(key=lambda r: (r["patient_id"], r["date"]))
    alarms.sort(key=lambda a: (a["patient_id"], a["raised_at"]))
    return {
        "simulated": True,
        "seed": seed,
        "generated_for_end_date": end.isoformat(),
        "patients": patients_out,
        "daily": daily,
        "alarms": alarms,
    }


def write(history: dict, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(history, indent=2) + "\n")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Generate fictional, simulated feeding history (demo data)."
    )
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument(
        "--end-date", type=date.fromisoformat, default=None,
        help="YYYY-MM-DD, default today (UTC)",
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    if args.days < 1:
        parser.error("--days must be at least 1")

    history = generate(days=args.days, seed=args.seed, end_date=args.end_date)
    write(history, args.out)
    print(
        f"Wrote simulated history to {args.out}: "
        f"{len(history['patients'])} patients x {args.days} days "
        f"ending {history['generated_for_end_date']}, "
        f"{len(history['alarms'])} alarms (seed {args.seed})."
    )


if __name__ == "__main__":
    main()
