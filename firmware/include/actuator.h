#pragma once
#include <Arduino.h>
#include "config.h"

#if DELIVERY_SIMULATED != 1
#error "This build implements digital delivery only; a calibrated physical actuator is required."
#endif

// An LED indicates activity. Delivery is computed by PumpController, not measured.
class Actuator {
 public:
  void begin() { pinMode(PIN_STEP, OUTPUT); stop(); }
  void setRateMlHr(double rate) { rateMlHr_ = rate; }
  void start() { running_ = rateMlHr_ > 0; }
  void stop() { running_ = false; digitalWrite(PIN_STEP, LOW); }
  void tick(uint32_t now) {
    digitalWrite(PIN_STEP, running_ && ((now / 250) % 2) ? HIGH : LOW);
  }
 private:
  bool running_ = false;
  double rateMlHr_ = 0;
};
