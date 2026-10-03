// Pins and tunables. Credentials go in secrets.h, not here.
#pragma once

#define PUMP_ID "pump-001"            // must match PUMP_ID in .env

constexpr unsigned long STATUS_INTERVAL_MS = 2000;
constexpr unsigned long NETWORK_RETRY_INTERVAL_MS = 5000;
constexpr unsigned long NETWORK_SHUTDOWN_TIMEOUT_MS = 3000;
constexpr unsigned long NETWORK_COMMAND_TIMEOUT_MS = 1000;
constexpr unsigned int MQTT_BUFFER_SIZE = 2048;
constexpr unsigned int MQTT_TASK_STACK_SIZE = 8192;
constexpr unsigned int MQTT_EVENT_QUEUE_LENGTH = 32;
constexpr unsigned int MQTT_INBOUND_QUEUE_LENGTH = 8;
constexpr unsigned long PRIMING_DURATION_MS = 1000;
constexpr unsigned long COMPLETE_DURATION_MS = 1000;
constexpr unsigned long BUTTON_DEBOUNCE_MS = 40;
constexpr unsigned long BUTTON_STOP_HOLD_MS = 1500;

// Set to 1 when there is no real pump head attached and delivery is modelled
// from time and rate. Status and event messages then carry "simulated": true.
#define DELIVERY_SIMULATED 1

// Pin assignments: placeholders, confirm against your wiring before use.
constexpr int PIN_STEP = 25;          // stepper driver STEP (or LED stand-in)
constexpr int PIN_DIR = 26;           // stepper driver DIR
constexpr int PIN_BTN_OCCLUSION = 32; // fault injection: occlusion
constexpr int PIN_BTN_BAG_EMPTY = 33; // fault injection: bag empty
constexpr int PIN_BTN_PAUSE = 27;     // caregiver pause / resume / confirm
constexpr int PIN_LEVEL_TOUCH = 4;    // T0: foil strip capacitive level sensor (optional)

// Calibrate by running a fixed number of steps into a measuring cup.
constexpr float STEPS_PER_ML = 100.0f; // placeholder until calibrated
