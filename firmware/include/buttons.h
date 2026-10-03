#pragma once
#include <Arduino.h>
#include "config.h"

class Button {
 public:
  explicit Button(int pin) : pin_(pin) {}
  void begin() { pinMode(pin_, INPUT_PULLUP); }
  // Act on release so a long stop does not also resume the feed.
  void tick(uint32_t now) {
    shortPress_ = longPress_ = false;
    const bool sample = digitalRead(pin_) == LOW;
    if (sample != raw_) { raw_ = sample; changedAt_ = now; }
    if (sample != pressed_ && now - changedAt_ >= BUTTON_DEBOUNCE_MS) {
      pressed_ = sample;
      if (pressed_) { pressedAt_ = now; held_ = false; }
      else if (!held_) shortPress_ = true;
    }
    if (pressed_ && !held_ && now - pressedAt_ >= BUTTON_STOP_HOLD_MS) {
      held_ = true; longPress_ = true;
    }
  }
  bool shortPress() const { return shortPress_; }
  bool longPress() const { return longPress_; }
 private:
  int pin_;
  bool raw_ = false, pressed_ = false, held_ = false;
  bool shortPress_ = false, longPress_ = false;
  uint32_t changedAt_ = 0, pressedAt_ = 0;
};
