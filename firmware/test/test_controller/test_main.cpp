#include <ArduinoJson.h>
#include <unity.h>

#include <cmath>
#include <limits>
#include <string>
#include <vector>

#include "prescription.h"
#include "pump_controller.h"

namespace {
const char* PUMP = "pump-001";
std::vector<PumpEvent> events;
std::vector<Prescription> writes;
bool writeSucceeds;

Prescription sample(uint32_t version = 1, double rate = 90, double volume = 100) {
  Prescription p;
  p.version = version;
  p.mode = "continuous";
  p.rateMlHr = rate;
  p.volumeMl = volume;
  p.proposedBy = "clinician-demo";
  p.proposedAt = "2026-10-03T12:00:00Z";
  p.confirmedBy = "caregiver-demo";
  p.confirmedAt = "2026-10-03T12:00:01-04:00";
  return p;
}

std::string json(uint32_t version = 1, double rate = 90, double volume = 100) {
  return serializePrescription(sample(version, rate, volume), PUMP);
}

std::string encode(JsonDocument& doc) {
  std::string output;
  serializeJson(doc, output);
  return output;
}

PrescriptionValidation parse(const std::string& input, uint32_t current = 0,
                             uint32_t pending = 0) {
  return parsePrescription(input.c_str(), input.size(), PUMP, current, pending);
}

void rejected(const std::string& input, const char* reason,
              uint32_t current = 0, uint32_t pending = 0) {
  const auto result = parse(input, current, pending);
  TEST_ASSERT_EQUAL(PrescriptionValidation::REJECTED, result.outcome);
  TEST_ASSERT_EQUAL_STRING(reason, result.reason.c_str());
}

PumpController controller(bool simulated = true, uint32_t prime = 10,
                          uint32_t complete = 20) {
  return PumpController(PUMP, simulated, prime, complete,
      [](const PumpEvent& event) { events.push_back(event); },
      [](const Prescription& prescription) {
        writes.push_back(prescription);
        return writeSucceeds;
      });
}

PrescriptionValidation receive(PumpController& c, const std::string& value,
                              uint32_t now = 0) {
  return c.receivePrescription(value.c_str(), value.size(), now);
}

void valid_prescription_roundtrips_and_accepts_limit_boundaries() {
  Prescription p = sample(4294967295U, 1, 1000);
  p.mode = "bolus";
  p.note = "caregiver checked";
  auto result = parse(serializePrescription(p, PUMP));
  TEST_ASSERT_EQUAL(PrescriptionValidation::ACCEPTED, result.outcome);
  TEST_ASSERT_EQUAL_UINT32(p.version, result.prescription.version);
  TEST_ASSERT_EQUAL_STRING(p.note.c_str(), result.prescription.note.c_str());
  TEST_ASSERT_EQUAL(PrescriptionValidation::ACCEPTED, parse(json(1, 150, 1)).outcome);
}

void shape_and_extra_fields_precede_other_checks() {
  rejected("{}", "malformed");
  rejected("[]", "malformed");
  rejected("null", "malformed");
  rejected(json() + "junk", "malformed");
  rejected(json() + json(), "malformed");
  JsonDocument doc;
  deserializeJson(doc, json());
  doc["pump_id"] = "wrong";
  doc["unexpected"] = true;
  rejected(encode(doc), "malformed");
  doc.remove("unexpected");
  doc.remove("proposed_by");
  rejected(encode(doc), "malformed");
  std::string escapedKey = json();
  escapedKey.insert(escapedKey.size() - 1, ",\"note\\u0000extra\":\"hidden\"");
  rejected(escapedKey, "malformed");
}

void malformed_types_and_schema_constraints() {
  const char* fields[] = {"pump_id", "version", "mode", "rate_ml_hr", "volume_ml",
      "proposed_by", "proposed_at", "confirmed_by", "confirmed_at", "note"};
  for (const char* field : fields) {
    JsonDocument doc;
    deserializeJson(doc, json());
    doc[field] = true;
    rejected(encode(doc), "malformed");
    doc[field] = nullptr;
    rejected(encode(doc), "malformed");
  }
  const char* numeric[] = {"version", "rate_ml_hr", "volume_ml"};
  for (const char* field : numeric) {
    JsonDocument doc;
    deserializeJson(doc, json());
    doc[field] = "90";
    rejected(encode(doc), "malformed");
    doc[field] = 0;
    rejected(encode(doc), "malformed");
    doc[field] = -1;
    rejected(encode(doc), "malformed");
  }
  JsonDocument doc;
  deserializeJson(doc, json());
  doc["version"] = 1.5;
  rejected(encode(doc), "malformed");
  doc["version"] = 4294967296.0;
  rejected(encode(doc), "malformed");
  doc["version"] = 1;
  doc["mode"] = "unsupported";
  rejected(encode(doc), "malformed");
  doc["mode"] = "bolus";
  doc["proposed_by"] = "";
  rejected(encode(doc), "malformed");
  doc["proposed_by"] = "clinician";
  doc["pump_id"] = "";
  rejected(encode(doc), "malformed");
}

void datetime_checks_calendar_timezone_and_fraction() {
  const char* invalid[] = {"", "yesterday", "2026-02-29T00:00:00Z",
      "2026-04-31T00:00:00Z", "2026-00-01T00:00:00Z", "2026-01-00T00:00:00Z",
      "2026-10-03T24:00:00Z", "2026-10-03T12:60:00Z", "2026-10-03T12:00:60Z",
      "2026-10-03T12:00:00", "2026-10-03T12:00:00+24:00",
      "2026-10-03T12:00:00+01:60", "2026-10-03T12:00:00.Z",
      "2026-10-03T12:00:00Zsuffix", "0000-01-01T12:00:00Z"};
  for (const char* date : invalid) {
    JsonDocument doc;
    deserializeJson(doc, json());
    doc["proposed_at"] = date;
    rejected(encode(doc), "malformed");
  }
  const char* valid[] = {"2024-02-29T23:59:59.125Z", "2000-02-29t00:00:00z",
                         "2026-10-03T12:00:00+05:30"};
  for (const char* date : valid) {
    JsonDocument doc;
    deserializeJson(doc, json());
    doc["proposed_at"] = date;
    TEST_ASSERT_EQUAL(PrescriptionValidation::ACCEPTED, parse(encode(doc)).outcome);
  }
  JsonDocument doc;
  deserializeJson(doc, json());
  doc["confirmed_at"] = "invalid-date";
  rejected(encode(doc), "malformed");
}

void confirmation_and_pump_order() {
  JsonDocument doc;
  deserializeJson(doc, json());
  doc["pump_id"] = "different";
  doc.remove("confirmed_by");
  doc.remove("confirmed_at");
  rejected(encode(doc), "wrong_pump");
  doc["pump_id"] = PUMP;
  rejected(encode(doc), "not_confirmed");
  doc["confirmed_by"] = "";
  doc["confirmed_at"] = "";
  rejected(encode(doc), "not_confirmed", 1);
  doc["confirmed_by"] = "caregiver";
  rejected(encode(doc), "not_confirmed");
}

void stale_replay_and_limit_order() {
  rejected(json(1, 500, 5000), "stale_version", 2);
  rejected(json(3, 500, 5000), "stale_version", 1, 3);
  rejected(json(3, 500, 5000), "rate_out_of_range", 1, 2);
  rejected(json(3, 90, 5000), "volume_out_of_range", 1, 2);
  rejected(json(3, 0.5, 100), "rate_out_of_range");
  rejected(json(3, 90, 0.5), "volume_out_of_range");
  TEST_ASSERT_EQUAL(PrescriptionValidation::IGNORED, parse(json(2, 500, 5000), 2, 3).outcome);
}

void note_length_counts_unicode_characters() {
  Prescription p = sample();
  p.note = std::string(200, 'x');
  TEST_ASSERT_EQUAL(PrescriptionValidation::ACCEPTED, parse(serializePrescription(p, PUMP)).outcome);
  p.note += 'x';
  rejected(serializePrescription(p, PUMP), "malformed");
  p.note.clear();
  for (unsigned i = 0; i < 200; ++i) p.note += "\xc3\xa9";
  TEST_ASSERT_EQUAL(PrescriptionValidation::ACCEPTED, parse(serializePrescription(p, PUMP)).outcome);
  p.note += "\xc3\xa9";
  rejected(serializePrescription(p, PUMP), "malformed");
}

void nonfinite_numbers_are_malformed() {
  std::string input = json();
  const size_t begin = input.find("90");
  TEST_ASSERT_NOT_EQUAL(std::string::npos, begin);
  input.replace(begin, 2, "1e400");
  rejected(input, "malformed");
  input = json();
  input.replace(input.find("90"), 2, "NaN");
  rejected(input, "malformed");
}

void javascript_extensions_and_raw_controls_are_not_json() {
  std::string input = json();
  size_t at = input.find("\"pump_id\"");
  input.replace(at, 9, "pump_id");
  rejected(input, "malformed");
  input = json();
  for (char& character : input) if (character == '"') character = '\'';
  rejected(input, "malformed");
  input = json();
  input.insert(input.size() - 1, ",");
  rejected(input, "malformed");
  const char* values[] = {"090", "+90", ".90", "90.", "90e", "0x90", "Infinity"};
  for (const char* value : values) {
    input = json();
    input.replace(input.find("90"), 2, value);
    rejected(input, "malformed");
  }
  input = json();
  input.insert(input.find("clinician-demo"), 1, '\n');
  rejected(input, "malformed");
  input = json();
  input.insert(input.find("clinician-demo"), 1, '\0');
  rejected(input, "malformed");
  input = json();
  input += std::string("\0suffix", 7);
  rejected(input, "malformed");
  input = json();
  input.insert(input.find("clinician-demo"), "\xc0\x80");
  rejected(input, "malformed");
  input = json();
  input.insert(input.find("clinician-demo"), "\xed\xa0\x80");
  rejected(input, "malformed");
  TEST_ASSERT_EQUAL(PrescriptionValidation::ACCEPTED, parse(" \n\t" + json() + "\r\n").outcome);
}

void idle_applies_only_after_successful_persistence() {
  auto c = controller();
  writeSucceeds = false;
  receive(c, json(), 10);
  TEST_ASSERT_FALSE(c.snapshot().hasPrescription);
  TEST_ASSERT_TRUE(c.snapshot().hasPending);
  TEST_ASSERT_EQUAL_STRING("prescription_queued", events.back().type.c_str());
  TEST_ASSERT_FALSE(c.start(20));
  TEST_ASSERT_EQUAL(PumpState::IDLE, c.snapshot().state);
  writeSucceeds = true;
  c.tick(30);
  TEST_ASSERT_TRUE(c.snapshot().hasPrescription);
  TEST_ASSERT_FALSE(c.snapshot().hasPending);
  TEST_ASSERT_EQUAL_UINT32(1, c.snapshot().prescription.version);
  TEST_ASSERT_EQUAL_STRING("prescription_applied", events.back().type.c_str());
  TEST_ASSERT_EQUAL_UINT32(30, events.back().uptimeMs);
}

void update_persistence_failure_preserves_current_until_retry() {
  auto c = controller();
  receive(c, json());
  writeSucceeds = false;
  receive(c, json(2, 100));
  TEST_ASSERT_EQUAL_UINT32(1, c.snapshot().prescription.version);
  TEST_ASSERT_TRUE(c.snapshot().hasPending);
  TEST_ASSERT_FALSE(c.start(0));
  writeSucceeds = true;
  TEST_ASSERT_TRUE(c.start(10));
  TEST_ASSERT_EQUAL_UINT32(2, c.snapshot().prescription.version);
  TEST_ASSERT_EQUAL(PumpState::PRIMING, c.snapshot().state);
}

void never_start_without_prescription_or_durable_writer() {
  auto c = controller();
  TEST_ASSERT_FALSE(c.start(0));
  PumpController missingWriter(PUMP, true, 0, 0, {}, {});
  receive(missingWriter, json());
  TEST_ASSERT_FALSE(missingWriter.start(0));
  TEST_ASSERT_FALSE(missingWriter.snapshot().hasPrescription);
}

void busy_queue_replaces_only_with_newer_version() {
  auto c = controller();
  receive(c, json());
  c.start(0);
  c.tick(10);
  receive(c, json(3, 100), 11);
  TEST_ASSERT_EQUAL_UINT32(1, c.snapshot().prescription.version);
  TEST_ASSERT_EQUAL_UINT32(3, c.snapshot().pending.version);
  TEST_ASSERT_EQUAL_STRING("prescription_queued", events.back().type.c_str());
  receive(c, json(2), 12);
  TEST_ASSERT_EQUAL_STRING("stale_version", events.back().reason.c_str());
  receive(c, json(3), 13);
  TEST_ASSERT_EQUAL_STRING("stale_version", events.back().reason.c_str());
  receive(c, json(4, 110), 14);
  TEST_ASSERT_EQUAL_UINT32(4, c.snapshot().pending.version);
  TEST_ASSERT_EQUAL_UINT(1, writes.size());
  c.pause(15);
  c.tick(10000);
  TEST_ASSERT_EQUAL_UINT32(1, c.snapshot().prescription.version);
  c.stop(10001);
  TEST_ASSERT_EQUAL_UINT32(4, c.snapshot().prescription.version);
  TEST_ASSERT_FALSE(c.snapshot().hasPending);
  TEST_ASSERT_EQUAL(PumpState::IDLE, c.snapshot().state);
}

void current_replay_is_silent_but_confirmation_still_checked() {
  auto c = controller();
  receive(c, json());
  const size_t count = events.size();
  TEST_ASSERT_EQUAL(PrescriptionValidation::IGNORED, receive(c, json()).outcome);
  TEST_ASSERT_EQUAL_UINT(count, events.size());
  JsonDocument doc;
  deserializeJson(doc, json());
  doc.remove("confirmed_by");
  receive(c, encode(doc));
  TEST_ASSERT_EQUAL_STRING("not_confirmed", events.back().reason.c_str());
  TEST_ASSERT_EQUAL_UINT32(1, c.snapshot().prescription.version);
}

void reboot_restores_only_valid_prescription_and_stays_idle() {
  auto c = controller();
  const std::string stored = json(7, 100, 200);
  TEST_ASSERT_TRUE(c.restorePrescription(stored.c_str(), stored.size()));
  TEST_ASSERT_EQUAL_UINT32(7, c.snapshot().prescription.version);
  TEST_ASSERT_EQUAL(PumpState::IDLE, c.snapshot().state);
  TEST_ASSERT_EQUAL_UINT(0, writes.size());
  TEST_ASSERT_EQUAL_UINT(0, events.size());
  TEST_ASSERT_FALSE(c.restorePrescription(stored.c_str(), stored.size()));
  TEST_ASSERT_EQUAL(PrescriptionValidation::IGNORED, receive(c, stored).outcome);
  rejected(json(6), "stale_version", 7);
  auto invalid = controller();
  const std::string bad = json(8, 500);
  TEST_ASSERT_FALSE(invalid.restorePrescription(bad.c_str(), bad.size()));
  TEST_ASSERT_FALSE(invalid.start(0));
}

void simulated_delivery_pause_resume_and_completion() {
  auto c = controller(true, 100, 200);
  receive(c, json(1, 90, 1));
  TEST_ASSERT_TRUE(c.start(0));
  c.tick(99);
  TEST_ASSERT_EQUAL(PumpState::PRIMING, c.snapshot().state);
  TEST_ASSERT_FLOAT_WITHIN(1e-6, 0, c.snapshot().deliveredMl);
  c.tick(100);
  c.tick(20100);
  TEST_ASSERT_FLOAT_WITHIN(1e-6, 0.5, c.snapshot().deliveredMl);
  TEST_ASSERT_TRUE(c.pause(20100));
  c.tick(120100);
  TEST_ASSERT_FLOAT_WITHIN(1e-6, 0.5, c.snapshot().deliveredMl);
  TEST_ASSERT_TRUE(c.resume(120100));
  c.tick(140100);
  TEST_ASSERT_EQUAL(PumpState::COMPLETE, c.snapshot().state);
  TEST_ASSERT_FLOAT_WITHIN(1e-6, 1, c.snapshot().deliveredMl);
  c.tick(140299);
  TEST_ASSERT_EQUAL(PumpState::COMPLETE, c.snapshot().state);
  c.tick(140300);
  TEST_ASSERT_EQUAL(PumpState::IDLE, c.snapshot().state);
  TEST_ASSERT_TRUE(c.start(140301));
  TEST_ASSERT_FLOAT_WITHIN(1e-6, 0, c.snapshot().deliveredMl);
}

void alarm_clear_pauses_and_requires_caregiver_resume() {
  auto c = controller();
  receive(c, json());
  c.start(0);
  c.tick(10);
  TEST_ASSERT_TRUE(c.raiseAlarm("occlusion", 20));
  TEST_ASSERT_EQUAL(PumpState::ALARM, c.snapshot().state);
  TEST_ASSERT_EQUAL_STRING("alarm_raised", events.back().type.c_str());
  TEST_ASSERT_FALSE(c.raiseAlarm("bag_empty", 21));
  TEST_ASSERT_FALSE(c.resume(22));
  TEST_ASSERT_FALSE(c.stop(23));
  receive(c, json(2), 24);
  TEST_ASSERT_TRUE(c.clearAlarm(25));
  TEST_ASSERT_EQUAL(PumpState::PAUSED, c.snapshot().state);
  TEST_ASSERT_TRUE(c.snapshot().alarm.empty());
  c.tick(20000);
  TEST_ASSERT_EQUAL_UINT32(1, c.snapshot().prescription.version);
  TEST_ASSERT_TRUE(c.resume(20001));
  TEST_ASSERT_EQUAL(PumpState::RUNNING, c.snapshot().state);
  TEST_ASSERT_FALSE(c.raiseAlarm("invalid", 20002));
  TEST_ASSERT_TRUE(c.pause(20003));
  TEST_ASSERT_TRUE(c.stop(20004));
  TEST_ASSERT_EQUAL_UINT32(2, c.snapshot().prescription.version);
}

void timers_and_delivery_survive_millis_wrap() {
  auto c = controller(true, 10, 20);
  receive(c, json(1, 90, 1));
  const uint32_t beforeWrap = 4294967290U;
  c.start(beforeWrap);
  c.tick(3);
  TEST_ASSERT_EQUAL(PumpState::PRIMING, c.snapshot().state);
  c.tick(4);
  TEST_ASSERT_EQUAL(PumpState::RUNNING, c.snapshot().state);
  c.tick(20004);
  TEST_ASSERT_FLOAT_WITHIN(1e-6, 0.5, c.snapshot().deliveredMl);
  c.tick(40004);
  TEST_ASSERT_EQUAL(PumpState::COMPLETE, c.snapshot().state);
  c.tick(40024);
  TEST_ASSERT_EQUAL(PumpState::IDLE, c.snapshot().state);
}

void measured_delivery_rejects_invalid_deltas_and_stops_at_target() {
  auto c = controller(false);
  receive(c, json(1, 90, 1));
  c.start(0);
  c.tick(10);
  c.tick(1000000);
  TEST_ASSERT_FLOAT_WITHIN(1e-6, 0, c.snapshot().deliveredMl);
  c.tick(1000001, -1);
  c.tick(1000002, std::numeric_limits<double>::infinity());
  c.tick(1000003, std::numeric_limits<double>::quiet_NaN());
  TEST_ASSERT_FLOAT_WITHIN(1e-6, 0, c.snapshot().deliveredMl);
  c.tick(1000004, 0.25);
  TEST_ASSERT_FLOAT_WITHIN(1e-6, 0.25, c.snapshot().deliveredMl);
  c.tick(1000005, 100);
  TEST_ASSERT_FLOAT_WITHIN(1e-6, 1, c.snapshot().deliveredMl);
  TEST_ASSERT_EQUAL(PumpState::COMPLETE, c.snapshot().state);
  c.tick(1000006, 100);
  TEST_ASSERT_FLOAT_WITHIN(1e-6, 1, c.snapshot().deliveredMl);
}

void completion_returns_idle_and_applies_pending() {
  auto c = controller(false, 0, 20);
  receive(c, json(1, 90, 1));
  c.start(0);
  c.tick(0);
  receive(c, json(2, 100, 2));
  c.tick(1, 1);
  TEST_ASSERT_EQUAL_UINT32(1, c.snapshot().prescription.version);
  c.tick(20);
  TEST_ASSERT_EQUAL_UINT32(1, c.snapshot().prescription.version);
  c.tick(21);
  TEST_ASSERT_EQUAL(PumpState::IDLE, c.snapshot().state);
  TEST_ASSERT_EQUAL_UINT32(2, c.snapshot().prescription.version);
  TEST_ASSERT_FLOAT_WITHIN(1e-6, 0, c.snapshot().deliveredMl);
}

void malformed_unversioned_input_never_fabricates_rejection_version() {
  auto c = controller();
  auto result = receive(c, "broken-json");
  TEST_ASSERT_EQUAL_STRING("malformed", result.reason.c_str());
  TEST_ASSERT_EQUAL_UINT32(0, result.version);
  TEST_ASSERT_EQUAL_UINT(0, events.size());
  JsonDocument doc;
  deserializeJson(doc, json(9));
  doc["unknown"] = 1;
  result = receive(c, encode(doc));
  TEST_ASSERT_EQUAL_UINT32(9, result.version);
  TEST_ASSERT_EQUAL_UINT32(9, events.back().version);
  TEST_ASSERT_EQUAL_STRING("prescription_rejected", events.back().type.c_str());
}
}  // namespace

void setUp() {
  events.clear();
  writes.clear();
  writeSucceeds = true;
}

void tearDown() {
  for (const auto& event : events) {
    TEST_ASSERT_EQUAL_STRING(PUMP, event.pumpId.c_str());
    if (event.type == "prescription_rejected" || event.type == "prescription_queued" ||
        event.type == "prescription_applied") TEST_ASSERT_GREATER_THAN_UINT32(0, event.version);
    if (event.type == "prescription_rejected") TEST_ASSERT_FALSE(event.reason.empty());
    if (event.type == "alarm_raised" || event.type == "alarm_cleared")
      TEST_ASSERT_FALSE(event.alarm.empty());
    if (event.type == "state_changed") TEST_ASSERT_NOT_EQUAL(event.fromState, event.toState);
  }
}

int main() {
  UNITY_BEGIN();
  RUN_TEST(valid_prescription_roundtrips_and_accepts_limit_boundaries);
  RUN_TEST(shape_and_extra_fields_precede_other_checks);
  RUN_TEST(malformed_types_and_schema_constraints);
  RUN_TEST(datetime_checks_calendar_timezone_and_fraction);
  RUN_TEST(confirmation_and_pump_order);
  RUN_TEST(stale_replay_and_limit_order);
  RUN_TEST(note_length_counts_unicode_characters);
  RUN_TEST(nonfinite_numbers_are_malformed);
  RUN_TEST(javascript_extensions_and_raw_controls_are_not_json);
  RUN_TEST(idle_applies_only_after_successful_persistence);
  RUN_TEST(update_persistence_failure_preserves_current_until_retry);
  RUN_TEST(never_start_without_prescription_or_durable_writer);
  RUN_TEST(busy_queue_replaces_only_with_newer_version);
  RUN_TEST(current_replay_is_silent_but_confirmation_still_checked);
  RUN_TEST(reboot_restores_only_valid_prescription_and_stays_idle);
  RUN_TEST(simulated_delivery_pause_resume_and_completion);
  RUN_TEST(alarm_clear_pauses_and_requires_caregiver_resume);
  RUN_TEST(timers_and_delivery_survive_millis_wrap);
  RUN_TEST(measured_delivery_rejects_invalid_deltas_and_stops_at_target);
  RUN_TEST(completion_returns_idle_and_applies_pending);
  RUN_TEST(malformed_unversioned_input_never_fabricates_rejection_version);
  return UNITY_END();
}
