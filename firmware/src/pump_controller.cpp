#include "pump_controller.h"

#include <algorithm>
#include <cmath>
#include <utility>

PumpController::PumpController(const std::string& pumpId, bool simulated,
                               uint32_t primingMs, uint32_t completeMs,
                               EventCallback eventCallback,
                               PersistCallback persistCallback)
    : pumpId_(pumpId), simulated_(simulated), primingMs_(primingMs),
      completeMs_(completeMs), eventCallback_(std::move(eventCallback)),
      persistCallback_(std::move(persistCallback)) {}

void PumpController::emit(PumpEvent event, uint32_t now) {
  event.pumpId = pumpId_;
  event.uptimeMs = now;
  event.simulated = simulated_;
  if (eventCallback_) eventCallback_(event);
}

void PumpController::transitionTo(PumpState state, uint32_t now) {
  if (snapshot_.state == state) return;
  PumpEvent event;
  event.type = "state_changed";
  event.fromState = snapshot_.state;
  event.toState = state;
  snapshot_.state = state;
  stateSinceMs_ = now;
  lastTickMs_ = now;
  emit(event, now);
}

bool PumpController::applyPending(uint32_t now) {
  if (snapshot_.state != PumpState::IDLE || !snapshot_.hasPending) return false;
  // A failed durable write must never be reported as active. Keep it for retry.
  if (!persistCallback_ || !persistCallback_(snapshot_.pending)) return false;
  snapshot_.prescription = snapshot_.pending;
  snapshot_.hasPrescription = true;
  snapshot_.hasPending = false;
  snapshot_.pending = Prescription();
  snapshot_.deliveredMl = 0;
  PumpEvent event;
  event.type = "prescription_applied";
  event.version = snapshot_.prescription.version;
  emit(event, now);
  return true;
}

PrescriptionValidation PumpController::receivePrescription(const char* payload,
                                                            size_t length,
                                                            uint32_t now) {
  PrescriptionValidation result = parsePrescription(payload, length, pumpId_,
      snapshot_.hasPrescription ? snapshot_.prescription.version : 0,
      snapshot_.hasPending ? snapshot_.pending.version : 0);
  if (result.outcome == PrescriptionValidation::IGNORED) return result;
  PumpEvent event;
  event.version = result.version;
  if (result.outcome == PrescriptionValidation::REJECTED) {
    event.type = "prescription_rejected";
    event.reason = result.reason;
    // The frozen event schema requires a positive version. The caller can log
    // unversioned malformed input, without falsely rejecting an unrelated v1.
    if (event.version) {
      snapshot_.lastRejectedVersion = event.version;
      snapshot_.lastRejectReason = event.reason;
      emit(event, now);
    }
    return result;
  }
  snapshot_.pending = result.prescription;
  snapshot_.hasPending = true;
  if (snapshot_.state != PumpState::IDLE || !applyPending(now)) {
    event.type = "prescription_queued";
    emit(event, now);
  }
  return result;
}

bool PumpController::restorePrescription(const char* payload, size_t length) {
  // Restore is a boot operation, never a way to replace an active prescription.
  if (snapshot_.state != PumpState::IDLE || snapshot_.hasPrescription ||
      snapshot_.hasPending) return false;
  const PrescriptionValidation result = parsePrescription(payload, length, pumpId_, 0);
  if (result.outcome != PrescriptionValidation::ACCEPTED) return false;
  snapshot_.prescription = result.prescription;
  snapshot_.hasPrescription = true;
  return true;
}

bool PumpController::start(uint32_t now) {
  if (snapshot_.state != PumpState::IDLE) return false;
  if (snapshot_.hasPending && !applyPending(now)) return false;
  if (!snapshot_.hasPrescription) return false;
  snapshot_.deliveredMl = 0;
  transitionTo(PumpState::PRIMING, now);
  return true;
}

bool PumpController::pause(uint32_t now) {
  if (snapshot_.state != PumpState::PRIMING && snapshot_.state != PumpState::RUNNING)
    return false;
  advanceDelivery(now, 0);
  if (snapshot_.state == PumpState::COMPLETE) return false;
  transitionTo(PumpState::PAUSED, now);
  return true;
}

bool PumpController::resume(uint32_t now) {
  if (snapshot_.state != PumpState::PAUSED || !snapshot_.hasPrescription ||
      !snapshot_.alarm.empty()) return false;
  transitionTo(PumpState::RUNNING, now);
  return true;
}

bool PumpController::stop(uint32_t now) {
  // Alarm acknowledgement must go through clearAlarm before cancellation/resume.
  if (snapshot_.state == PumpState::ALARM || snapshot_.state == PumpState::IDLE)
    return false;
  advanceDelivery(now, 0);
  transitionTo(PumpState::IDLE, now);
  applyPending(now);
  return true;
}

bool PumpController::raiseAlarm(const char* alarm, uint32_t now) {
  if (snapshot_.state != PumpState::RUNNING && snapshot_.state != PumpState::PAUSED)
    return false;
  if (!alarm) return false;
  const std::string name(alarm);
  if (name != "occlusion" && name != "bag_empty" && name != "low_battery" &&
      name != "sensor_mismatch") return false;
  if (snapshot_.state == PumpState::ALARM) return false;
  advanceDelivery(now, 0);
  snapshot_.alarm = name;
  PumpEvent event;
  event.type = "alarm_raised";
  event.alarm = name;
  emit(event, now);
  transitionTo(PumpState::ALARM, now);
  return true;
}

bool PumpController::clearAlarm(uint32_t now) {
  if (snapshot_.state != PumpState::ALARM || snapshot_.alarm.empty()) return false;
  PumpEvent event;
  event.type = "alarm_cleared";
  event.alarm = snapshot_.alarm;
  snapshot_.alarm.clear();
  emit(event, now);
  transitionTo(PumpState::PAUSED, now);
  return true;
}

void PumpController::advanceDelivery(uint32_t now, double measuredDeltaMl) {
  if (snapshot_.state != PumpState::RUNNING) return;
  const uint32_t elapsed = now - lastTickMs_;
  lastTickMs_ = now;
  const double delta = simulated_ ? snapshot_.prescription.rateMlHr * elapsed / 3600000.0
                                  : measuredDeltaMl;
  if (!std::isfinite(delta) || delta < 0) return;
  const double remaining = snapshot_.prescription.volumeMl - snapshot_.deliveredMl;
  snapshot_.deliveredMl += std::min(delta, remaining);
  if (snapshot_.deliveredMl >= snapshot_.prescription.volumeMl)
    transitionTo(PumpState::COMPLETE, now);
}

void PumpController::tick(uint32_t now, double measuredDeltaMl) {
  if (snapshot_.state == PumpState::PRIMING) {
    if (static_cast<uint32_t>(now - stateSinceMs_) >= primingMs_)
      transitionTo(PumpState::RUNNING, now);
  } else if (snapshot_.state == PumpState::RUNNING) {
    advanceDelivery(now, measuredDeltaMl);
  } else if (snapshot_.state == PumpState::COMPLETE) {
    if (static_cast<uint32_t>(now - stateSinceMs_) >= completeMs_)
      transitionTo(PumpState::IDLE, now);
  }
  if (snapshot_.state == PumpState::IDLE) applyPending(now);
}
