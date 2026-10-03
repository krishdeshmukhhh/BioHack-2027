// Deterministic desktop harness for the same controller that runs on the ESP32.
// stdin: JSON commands, stdout: {topic,payload} protocol envelopes.
#ifndef PIO_UNIT_TESTING
#include <ArduinoJson.h>
#include <cstdio>
#include <fstream>
#include <iostream>
#include <iterator>
#include <string>
#include "config.h"
#include "demo_fixture.h"
#include "pump_controller.h"
#include "telemetry.h"

namespace {
void output(const std::string& topic, const std::string& payload) {
  JsonDocument envelope;
  envelope["topic"] = topic;
  JsonDocument body;
  if (deserializeJson(body, payload)) envelope["payload"] = payload;
  else envelope["payload"] = body.as<JsonVariant>();
  serializeJson(envelope, std::cout);
  std::cout << std::endl;
}
}  // namespace

int main(int argc, char** argv) {
  const std::string store = argc > 1 ? argv[1] : "";
  uint32_t now = 0;
  const std::string topic = std::string("pump/") + PUMP_ID;
  auto persist = [&store](const Prescription& prescription) {
    if (store.empty()) return true;  // Explicit ephemeral mode for tests/demo.
    const std::string staging = store + ".tmp";
    std::ofstream file(staging, std::ios::binary | std::ios::trunc);
    file << serializePrescription(prescription, PUMP_ID);
    file.close();
    return !file.fail() && std::rename(staging.c_str(), store.c_str()) == 0;
  };
  PumpController controller(PUMP_ID, true, PRIMING_DURATION_MS, COMPLETE_DURATION_MS,
    [&topic](const PumpEvent& event) { output(topic + "/event", eventJson(event)); }, persist);
  if (!store.empty()) {
    std::ifstream file(store, std::ios::binary);
    const std::string saved((std::istreambuf_iterator<char>(file)), std::istreambuf_iterator<char>());
    if (!saved.empty() && !controller.restorePrescription(saved.data(), saved.size())) {
      std::cerr << "Stored prescription invalid; remaining idle without a prescription.\n";
    }
  }
  output(topic + "/availability", "online");
  output(topic + "/status", statusJson(controller.snapshot(), PUMP_ID, now, true));
  std::string line;
  while (std::getline(std::cin, line)) {
    JsonDocument request;
    if (deserializeJson(request, line) || !request.is<JsonObject>()) {
      std::cerr << "Expected a JSON command object.\n";
      continue;
    }
    const std::string command = request["command"] | "";
    bool accepted = true;
    if (command == "prescription") {
      std::string payload;
      if (request["payload"].is<const char*>()) payload = request["payload"].as<std::string>();
      else serializeJson(request["payload"], payload);
      const auto result = controller.receivePrescription(payload.data(), payload.size(), now);
      if (result.outcome == PrescriptionValidation::REJECTED && !result.version) {
        std::cerr << "Rejected unversioned malformed input; event schema needs an identifiable version.\n";
      }
    } else if (command == "tick" && request["elapsed_ms"].is<uint32_t>()) {
      now += request["elapsed_ms"].as<uint32_t>();
      controller.tick(now);
    } else if (command == "demo") accepted = loadDemoPrescription(controller, PUMP_ID, now);
    else if (command == "start") accepted = controller.start(now);
    else if (command == "pause") accepted = controller.pause(now);
    else if (command == "resume") accepted = controller.resume(now);
    else if (command == "stop") accepted = controller.stop(now);
    else if (command == "occlusion" || command == "bag_empty") {
      accepted = controller.raiseAlarm(command.c_str(), now);
    } else if (command == "clear") accepted = controller.clearAlarm(now);
    else if (command != "status") accepted = false;
    if (!accepted) std::cerr << "Command unavailable in current state: " << command << '\n';
    output(topic + "/status", statusJson(controller.snapshot(), PUMP_ID, now, true));
  }
  output(topic + "/availability", "offline");
  return 0;
}
#endif
