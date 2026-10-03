# Simulator and demo data

- `pump_sim.py`: a software pump that behaves exactly like the firmware on MQTT, with fault injection and scripted scenarios. Lets the hub and web apps be built before hardware is ready, and is the fallback if hardware fails on demo day.
- `generate_history.py`: 30 days of fictional history for the clinician dashboard.

Everything here is flagged `"simulated": true`.
