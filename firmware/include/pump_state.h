// Pump states. Names must match the "state" enum in shared/protocol/status.schema.json.
#pragma once

enum class PumpState { IDLE, PRIMING, RUNNING, PAUSED, ALARM, COMPLETE };

inline const char* toString(PumpState s) {
  switch (s) {
    case PumpState::IDLE: return "idle";
    case PumpState::PRIMING: return "priming";
    case PumpState::RUNNING: return "running";
    case PumpState::PAUSED: return "paused";
    case PumpState::ALARM: return "alarm";
    case PumpState::COMPLETE: return "complete";
  }
  return "idle";
}
