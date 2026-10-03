// Hard safety limits (safety invariant S1).
//
// These are compile-time constants on purpose. They must never be settable
// over MQTT, HTTP, or serial. A prescription outside these limits is rejected
// and reported, never clamped.
//
// DEMO VALUES ONLY. These are not clinical guidance.
#pragma once

constexpr float LIMIT_RATE_MIN_ML_HR = 1.0f;
constexpr float LIMIT_RATE_MAX_ML_HR = 150.0f;
constexpr float LIMIT_VOLUME_MIN_ML = 1.0f;
constexpr float LIMIT_VOLUME_MAX_ML = 1000.0f;
