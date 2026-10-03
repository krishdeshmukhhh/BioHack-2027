#pragma once
#include <climits>
#include "pump_controller.h"

// Explicit local demo command: fixed fictional confirmation and test values.
// It never starts delivery. Only the digitally simulated build uses this helper.
inline bool loadDemoPrescription(PumpController& controller, const char* pumpId, uint32_t now) {
  const auto& before = controller.snapshot();
  if (before.state != PumpState::IDLE || before.hasPending) return false;
  const uint32_t current = before.hasPrescription ? before.prescription.version : 0;
  if (current >= INT32_MAX) return false;
  Prescription fixture;
  fixture.version = current + 1;
  fixture.mode = "continuous";
  fixture.rateMlHr = 60;
  fixture.volumeMl = 5;
  fixture.proposedBy = "clinician-demo";
  fixture.proposedAt = "2026-10-03T00:00:00Z";
  fixture.confirmedBy = "local-caregiver-demo";
  fixture.confirmedAt = "2026-10-03T00:00:01Z";
  fixture.note = "Explicit serial demo confirmation; simulated delivery only";
  const std::string payload = serializePrescription(fixture, pumpId);
  const auto result = controller.receivePrescription(payload.data(), payload.size(), now);
  return result.outcome == PrescriptionValidation::ACCEPTED &&
         controller.snapshot().hasPrescription &&
         controller.snapshot().prescription.version == fixture.version;
}
