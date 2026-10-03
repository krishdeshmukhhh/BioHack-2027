"""Software pump simulator. Scaffold only: see docs/PLAN.md phase 1.

Must be indistinguishable from the ESP32 firmware on MQTT: same topics, same
schemas, same state machine, same validation order and rejection reasons, and
the same limits as firmware/include/limits.h. Everything it sends carries
"simulated": true.
"""

# Keep in step with firmware/include/limits.h. Demo values, not clinical guidance.
LIMIT_RATE_MIN_ML_HR = 1.0
LIMIT_RATE_MAX_ML_HR = 150.0
LIMIT_VOLUME_MIN_ML = 1.0
LIMIT_VOLUME_MAX_ML = 1000.0


def main() -> None:
    raise SystemExit("pump_sim is not implemented yet. See docs/PLAN.md phase 1.")


if __name__ == "__main__":
    main()
