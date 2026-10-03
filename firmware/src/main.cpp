// Smart pump firmware scaffold. See docs/PLAN.md phase 3 and .claude/rules/firmware.md.
#include <Arduino.h>

#include "config.h"
#include "limits.h"
#include "pump_state.h"

static PumpState state = PumpState::IDLE;
static unsigned long lastStatusMs = 0;

void setup() {
  Serial.begin(115200);
  Serial.println("smart-pump firmware scaffold");
  // TODO phase 3: wifi + MQTT (with Last Will), load prescription from NVS,
  // set up buttons, actuator, and display.
}

void loop() {
  // Never block here. Use millis() timers.
  const unsigned long now = millis();
  if (now - lastStatusMs >= STATUS_INTERVAL_MS) {
    lastStatusMs = now;
    Serial.printf("state=%s\n", toString(state));
    // TODO phase 3: publish status to pump/{id}/status.
  }
}
