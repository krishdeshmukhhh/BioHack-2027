#pragma once

#include <stddef.h>

// The network task owns WiFi and MQTT. These functions only copy bounded queue
// items and never wait for a broker, socket, or FreeRTOS queue.
namespace mqtt_link {
// Best-effort serial diagnostic, drained by the network task, never by delivery.
void logLine(const char* line);
bool begin();

// A false result leaves the queue unchanged, including when capacity is too
// small. Use MQTT_BUFFER_SIZE + 1 bytes. length excludes the terminating NUL.
// Embedded NULs are converted to malformed JSON so C-string consumers cannot
// accidentally accept a valid prefix of an invalid prescription.
bool receivePrescription(char* buffer, size_t capacity, size_t* length = nullptr);

// Status replaces the previous unsent status. Events preserve FIFO order until
// the broker acknowledges QoS 1. False means full, oversized, or not started;
// callers must retain/retry events they need delivered. RAM queues do not
// survive reboot, and QoS 1 may deliver an event more than once.
bool publishStatus(const char* json);
bool publishEvent(const char* json);
bool connected();

// Stop the actuator before requesting a restart. Offline is published retained
// at QoS 1 before disconnecting; failed delivery falls back to the Last Will.
// This only queues the request; the calling task continues without waiting.
void requestShutdown(bool restart = false);
}  // namespace mqtt_link
