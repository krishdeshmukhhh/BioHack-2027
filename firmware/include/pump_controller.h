#pragma once

#include <cstddef>
#include <cstdint>
#include <functional>
#include <string>

#include "prescription.h"
#include "pump_state.h"

struct PumpEvent {
  std::string pumpId;
  uint32_t uptimeMs = 0;
  std::string type;
  bool simulated = true;
  uint32_t version = 0;  // Omit when zero.
  std::string reason;   // Omit when empty.
  std::string alarm;    // Omit when empty.
  PumpState fromState = PumpState::IDLE;
  PumpState toState = PumpState::IDLE;
};

struct PumpSnapshot {
  PumpState state = PumpState::IDLE;
  bool hasPrescription = false;
  Prescription prescription;
  bool hasPending = false;
  Prescription pending;
  double deliveredMl = 0;
  std::string alarm;
};

class PumpController {
 public:
  typedef std::function<void(const PumpEvent&)> EventCallback;
  typedef std::function<bool(const Prescription&)> PersistCallback;

  PumpController(const std::string& pumpId, bool simulated,
                 uint32_t primingMs, uint32_t completeMs,
                 EventCallback eventCallback, PersistCallback persistCallback);

  PrescriptionValidation receivePrescription(const char* payload, size_t length,
                                             uint32_t now);
  bool restorePrescription(const char* payload, size_t length);
  bool start(uint32_t now);
  bool pause(uint32_t now);
  bool resume(uint32_t now);
  bool stop(uint32_t now);
  bool raiseAlarm(const char* alarm, uint32_t now);
  bool clearAlarm(uint32_t now);
  // Simulated delivery uses elapsed time. Physical delivery uses measuredDeltaMl.
  void tick(uint32_t now, double measuredDeltaMl = 0);
  const PumpSnapshot& snapshot() const { return snapshot_; }

 private:
  void transitionTo(PumpState state, uint32_t now);
  void emit(PumpEvent event, uint32_t now);
  bool applyPending(uint32_t now);
  void advanceDelivery(uint32_t now, double measuredDeltaMl);

  std::string pumpId_;
  bool simulated_;
  uint32_t primingMs_;
  uint32_t completeMs_;
  uint32_t stateSinceMs_ = 0;
  uint32_t lastTickMs_ = 0;
  EventCallback eventCallback_;
  PersistCallback persistCallback_;
  PumpSnapshot snapshot_;
};
