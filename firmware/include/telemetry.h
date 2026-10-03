#pragma once
#include <ArduinoJson.h>
#include <string>
#include "pump_controller.h"

inline std::string statusJson(const PumpSnapshot& s, const std::string& pumpId,
                              uint32_t now, bool simulated) {
  JsonDocument doc;
  doc["pump_id"] = pumpId;
  doc["uptime_ms"] = now;
  doc["state"] = toString(s.state);
  doc["rate_ml_hr"] = s.hasPrescription ? s.prescription.rateMlHr : 0;
  doc["delivered_ml"] = s.deliveredMl;
  doc["target_ml"] = s.hasPrescription ? s.prescription.volumeMl : 0;
  if (s.alarm.empty()) doc["alarm"] = nullptr;
  else doc["alarm"] = s.alarm;
  doc["prescription_version"] = s.hasPrescription ? s.prescription.version : 0;
  if (s.hasPending) doc["pending_version"] = s.pending.version;
  else doc["pending_version"] = nullptr;
  doc["simulated"] = simulated;
  std::string result;
  serializeJson(doc, result);
  return result;
}

inline std::string eventJson(const PumpEvent& e) {
  JsonDocument doc;
  doc["pump_id"] = e.pumpId;
  doc["uptime_ms"] = e.uptimeMs;
  doc["type"] = e.type;
  doc["simulated"] = e.simulated;
  if (e.version) doc["version"] = e.version;
  if (!e.reason.empty()) doc["reason"] = e.reason;
  if (!e.alarm.empty()) doc["alarm"] = e.alarm;
  if (e.type == "state_changed") {
    doc["from_state"] = toString(e.fromState);
    doc["to_state"] = toString(e.toState);
  }
  std::string result;
  serializeJson(doc, result);
  return result;
}
