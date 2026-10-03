#pragma once

#include <cstddef>
#include <cstdint>
#include <string>

struct Prescription {
  uint32_t version = 0;
  std::string mode;
  double rateMlHr = 0;
  double volumeMl = 0;
  std::string proposedBy;
  std::string proposedAt;
  std::string confirmedBy;
  std::string confirmedAt;
  std::string note;
};

struct PrescriptionValidation {
  enum Outcome { ACCEPTED, IGNORED, REJECTED };
  Outcome outcome = REJECTED;
  Prescription prescription;
  // Zero means no schema-valid version could be identified for an event.
  uint32_t version = 0;
  std::string reason;
};

PrescriptionValidation parsePrescription(const char* payload, size_t length,
                                        const std::string& pumpId,
                                        uint32_t currentVersion,
                                        uint32_t pendingVersion = 0);
std::string serializePrescription(const Prescription& prescription,
                                  const std::string& pumpId);
