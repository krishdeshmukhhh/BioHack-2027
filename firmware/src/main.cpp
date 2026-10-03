// ESP32 controller with digitally modelled delivery. Prototype/demo only.
#include <Arduino.h>
#include <Preferences.h>
#include <deque>
#include <string>
#include "actuator.h"
#include "buttons.h"
#include "config.h"
#ifdef LOCAL_DEMO
#include "demo_fixture.h"
#endif
#include "mqtt_link.h"
#include "pump_controller.h"
#include "telemetry.h"

namespace {
Preferences preferences;
bool storageReady = false;
bool restarting = false;
Actuator actuator;
Button occlusion(PIN_BTN_OCCLUSION), bagEmpty(PIN_BTN_BAG_EMPTY), pauseButton(PIN_BTN_PAUSE);
uint32_t lastStatusMs = 0;
std::deque<std::string> pendingEvents;
constexpr size_t LOCAL_EVENT_LIMIT = 64;

// The network worker writes the UART; the delivery task only enqueues diagnostics.
void logLine(const char* line) {
  mqtt_link::logLine(line);
}

bool persistPrescription(const Prescription& prescription) {
  if (!storageReady) return false;
  const std::string data = serializePrescription(prescription, PUMP_ID);
  // One NVS key keeps the prescription and version atomic across a reboot.
  return preferences.putString("current", data.c_str()) == data.size();
}

void reportEvent(const PumpEvent& event) {
  const std::string json = eventJson(event);
  logLine(json.c_str());
  const bool prescriptionEvent = event.type.compare(0, 13, "prescription_") == 0;
  // Reserve room for versioned outcomes. Input backpressure below ensures one
  // queued version can still emit its applied event when it later becomes idle.
  const size_t limit = prescriptionEvent ? LOCAL_EVENT_LIMIT : LOCAL_EVENT_LIMIT - 4;
  if (pendingEvents.size() < limit) pendingEvents.push_back(json);
  else logLine("diagnostic event backlog full; latest state/alarm remains in telemetry");
}

PumpController controller(PUMP_ID, true, PRIMING_DURATION_MS, COMPLETE_DURATION_MS,
                          reportEvent, persistPrescription);

void toggleFeed(uint32_t now) {
  if (restarting) return;
  switch (controller.snapshot().state) {
    case PumpState::IDLE: controller.start(now); break;
    case PumpState::RUNNING:
    case PumpState::PRIMING: controller.pause(now); break;
    case PumpState::PAUSED: controller.resume(now); break;
    case PumpState::ALARM: controller.clearAlarm(now); break;
    case PumpState::COMPLETE: break;
  }
}

void handleCommand(const std::string& command, uint32_t now) {
  if (restarting) return;
  bool accepted = true;
  if (command == "demo") {
#ifdef LOCAL_DEMO
    accepted = pendingEvents.size() < LOCAL_EVENT_LIMIT - 4 &&
               loadDemoPrescription(controller, PUMP_ID, now);
    if (accepted) logLine("Confirmed local digital demo loaded. Enter start to simulate delivery.");
#else
    // A local version the hub never issued would make the portal show a false
    // "Active on pump" (S5). Only the esp32dev_offline build has this command.
    logLine("demo is only in the esp32dev_offline build (no hub). Use the portal.");
    accepted = false;
#endif
  } else if (command == "start") accepted = controller.start(now);
  else if (command == "pause") accepted = controller.pause(now);
  else if (command == "resume") accepted = controller.resume(now);
  else if (command == "stop") accepted = controller.stop(now);
  else if (command == "occlusion") accepted = controller.raiseAlarm("occlusion", now);
  else if (command == "bag_empty") accepted = controller.raiseAlarm("bag_empty", now);
  else if (command == "clear") accepted = controller.clearAlarm(now);
  else if (command == "status") {
    logLine(statusJson(controller.snapshot(), PUMP_ID, now, true).c_str());
  } else if (command == "reboot" && controller.snapshot().state == PumpState::IDLE) {
    restarting = true;
    mqtt_link::requestShutdown(true);
  } else logLine("commands: demo start pause resume stop occlusion bag_empty clear status reboot (idle)");
  if (!accepted) logLine("Command unavailable in current state. Load demo while idle before start; clear alarm before resume.");
}

void readConsole(uint32_t now) {
  static std::string line;
  for (int count = 0; count < 64 && Serial.available(); ++count) {
    const char ch = static_cast<char>(Serial.read());
    if (ch == '\n') { handleCommand(line, now); line.clear(); }
    else if (ch != '\r' && line.size() < 32) line += ch;
  }
}
}  // namespace

void setup() {
  Serial.setTxBufferSize(2048);
  Serial.begin(115200);
  Serial.println("Smart pump prototype: ESP32 with simulated delivery; no person connected.");
#ifdef LOCAL_DEMO
  Serial.println("Mode: offline bench; local demo enabled; simulated=true");
  Serial.println("For an offline test, enter demo then start (newline after each command).");
#else
  Serial.println("Mode: hub; local demo disabled; simulated=true");
  Serial.println("Confirm a prescription through the hub, then enter start to simulate delivery.");
#endif
  actuator.begin();
  occlusion.begin(); bagEmpty.begin(); pauseButton.begin();
#ifdef LOCAL_DEMO
  // Bench-created versions must never be restored by the hub-connected build.
  storageReady = preferences.begin("pump-bench", false);
#else
  storageReady = preferences.begin("pump", false);
#endif
  if (storageReady) {
    const String saved = preferences.getString("current", "");
    if (!saved.isEmpty() && !controller.restorePrescription(saved.c_str(), saved.length())) {
      Serial.println("stored prescription invalid; pump remains idle without an active prescription");
    }
  } else Serial.println("NVS unavailable; prescriptions cannot be applied");
  if (!mqtt_link::begin()) Serial.println("network worker unavailable; local controller remains operational");
}

void loop() {
  const uint32_t now = millis();
  if (restarting) return;
  controller.tick(now);
  char payload[MQTT_BUFFER_SIZE + 1];
  size_t length = 0;
  if (pendingEvents.size() < LOCAL_EVENT_LIMIT - 4 &&
      mqtt_link::receivePrescription(payload, sizeof(payload), &length)) {
    const auto result = controller.receivePrescription(payload, length, now);
    if (result.outcome == PrescriptionValidation::REJECTED && result.version == 0) {
      logLine("malformed prescription without identifiable version; cannot emit a versioned rejection");
    }
  }
  occlusion.tick(now); bagEmpty.tick(now); pauseButton.tick(now);
  if (occlusion.shortPress() || occlusion.longPress()) controller.raiseAlarm("occlusion", now);
  if (bagEmpty.shortPress() || bagEmpty.longPress()) controller.raiseAlarm("bag_empty", now);
  if (pauseButton.shortPress()) toggleFeed(now);
  if (pauseButton.longPress()) controller.stop(now);
  readConsole(now);
  const auto& s = controller.snapshot();
  actuator.setRateMlHr(s.hasPrescription ? s.prescription.rateMlHr : 0);
  if (s.state == PumpState::RUNNING) actuator.start();
  else actuator.stop();
  actuator.tick(now);
  if (!pendingEvents.empty() && mqtt_link::publishEvent(pendingEvents.front().c_str())) {
    pendingEvents.pop_front();
  }
  if (now - lastStatusMs >= STATUS_INTERVAL_MS) {
    lastStatusMs = now;
    const std::string json = statusJson(s, PUMP_ID, now, true);
    mqtt_link::publishStatus(json.c_str());
    logLine(json.c_str());
  }
}
