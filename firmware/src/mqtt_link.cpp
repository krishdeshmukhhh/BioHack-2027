#include "mqtt_link.h"

#include <Arduino.h>
#include <MQTT.h>
#include <WiFi.h>
#include <atomic>
#include <cstring>
#include <freertos/FreeRTOS.h>
#include <freertos/queue.h>
#include <freertos/task.h>
#ifdef BENCH_AP
#include <esp_netif_sta_list.h>
#include <esp_wifi.h>
#endif

#include "config.h"
#if __has_include("secrets.h")
#include "secrets.h"
#else
#include "secrets.example.h"
#endif

#if defined(BENCH_AP) && defined(LOCAL_DEMO)
#error "BENCH_AP is hub-connected and must not enable LOCAL_DEMO"
#endif
#ifdef BENCH_AP
#if !defined(BENCH_AP_SSID) || !defined(BENCH_AP_PASSWORD)
#error "BENCH_AP requires a private SSID and WPA2 password in secrets.h"
#endif
static_assert(sizeof(BENCH_AP_SSID) > 1 && sizeof(BENCH_AP_SSID) <= 33,
              "BENCH_AP SSID must contain 1 to 32 bytes");
static_assert(sizeof(BENCH_AP_PASSWORD) >= 9 && sizeof(BENCH_AP_PASSWORD) <= 64,
              "BENCH_AP requires a WPA2 password of 8 to 63 bytes");
#endif

namespace {
constexpr char kPrescriptionTopic[] = "pump/" PUMP_ID "/prescription";
constexpr char kStatusTopic[] = "pump/" PUMP_ID "/status";
constexpr char kEventTopic[] = "pump/" PUMP_ID "/event";
constexpr char kAvailabilityTopic[] = "pump/" PUMP_ID "/availability";

struct Message {
  size_t length;
  char payload[MQTT_BUFFER_SIZE + 1];
};
struct Diagnostic {
  char line[512];
};

QueueHandle_t inbound = nullptr;
QueueHandle_t events = nullptr;
QueueHandle_t status = nullptr;
QueueHandle_t diagnostics = nullptr;
std::atomic<bool> started{false};
std::atomic<bool> isConnected{false};
std::atomic<bool> shutdownRequested{false};
std::atomic<bool> restartRequested{false};
// Used only on the network task, including its synchronous MQTT callback.
#ifndef LOCAL_DEMO
bool replayRequired = false;
#endif

bool copyJson(Message& message, const char* json) {
  if (json == nullptr) return false;
  const size_t length = strnlen(json, sizeof(message.payload));
  if (length >= sizeof(message.payload)) return false;
  message.length = length;
  memcpy(message.payload, json, length + 1);
  return true;
}

#ifndef LOCAL_DEMO
void queueMalformed() {
  Message message{};
  message.length = 1;
  message.payload[0] = '{';
  if (xQueueSend(inbound, &message, 0) != pdTRUE) replayRequired = true;
}

void onPrescription(MQTTClient*, char topic[], char bytes[], int length) {
  if (strcmp(topic, kPrescriptionTopic) != 0) return;
  if (length < 0 || static_cast<size_t>(length) > MQTT_BUFFER_SIZE ||
      (length > 0 && (bytes == nullptr || memchr(bytes, '\0', length) != nullptr))) {
    queueMalformed();
    return;
  }
  Message message{};
  message.length = static_cast<size_t>(length);
  if (length > 0) memcpy(message.payload, bytes, message.length);
  // Never call MQTT, controller, or actuator code inside this callback. If the
  // queue is full, reconnect later to retrieve the retained latest command.
  if (xQueueSend(inbound, &message, 0) != pdTRUE) {
    replayRequired = true;
    Serial.println("MQTT prescription queue full; retained replay scheduled");
  }
}
#endif

#ifdef BENCH_AP
bool startBenchAccessPoint() {
  // Only the broker Mac joins this private network. Limiting it to one peer
  // makes DHCP station discovery unambiguous; never assume a DHCP address.
  const IPAddress apAddress(192, 168, 4, 1);
  if (!WiFi.mode(WIFI_AP) ||
      !WiFi.softAPConfig(apAddress, apAddress, IPAddress(255, 255, 255, 0)) ||
      !WiFi.softAP(BENCH_AP_SSID, BENCH_AP_PASSWORD, 1, 0, 1)) {
    WiFi.softAPdisconnect(true);
    return false;
  }
  Serial.println("ESP32 private test network ready");
  return true;
}

bool benchBrokerAddress(IPAddress& address) {
  wifi_sta_list_t stations{};
  esp_netif_sta_list_t leases{};
  if (esp_wifi_ap_get_sta_list(&stations) != ESP_OK || stations.num != 1 ||
      esp_netif_get_sta_list(&stations, &leases) != ESP_OK || leases.num != 1 ||
      leases.sta[0].ip.addr == 0) return false;
  address = IPAddress(leases.sta[0].ip.addr);
  return true;
}
#endif

void runNetwork() {
#ifdef LOCAL_DEMO
  // Offline bench builds must never attach locally made versions to a hub.
  // Keep the worker for serial diagnostics and reboot, with no WiFi/MQTT calls.
  Message discarded{};
  while (!shutdownRequested.load()) {
    Diagnostic diagnostic{};
    if (xQueueReceive(diagnostics, &diagnostic, 0) == pdTRUE) Serial.println(diagnostic.line);
    xQueueReceive(events, &discarded, 0);
    xQueueReceive(status, &discarded, 0);
    vTaskDelay(pdMS_TO_TICKS(10));
  }
#else
  WiFiClient socket;
  // ESP32 WiFiClient's socket timeout uses seconds; MQTT's uses milliseconds.
  socket.setTimeout(1);
  // R2: allocate packet buffers before any connection. arduino-mqtt
  // configures buffers in its constructor instead of setBufferSize().
  MQTTClient mqtt(MQTT_BUFFER_SIZE);
#ifdef BENCH_AP
  mqtt.begin(socket);
#else
  mqtt.begin(MQTT_HOST, MQTT_PORT, socket);
#endif
  mqtt.onMessageAdvanced(onPrescription);
  mqtt.setOptions(15, true, NETWORK_COMMAND_TIMEOUT_MS);
  mqtt.setWill(kAvailabilityTopic, "offline", true, 1);
  // Consume oversized packets intact, report malformed, and keep the link
  // usable. The library never passes a truncated payload to our callback.
  mqtt.dropOverflow(true);
  uint32_t droppedCount = 0;

#ifdef BENCH_AP
  bool apReady = startBenchAccessPoint();
  IPAddress brokerAddress;
  bool peerReady = false;
  constexpr unsigned long kPeerCheckIntervalMs = 250;
  unsigned long lastPeerCheck = millis() - kPeerCheckIntervalMs;
#else
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
#endif
  unsigned long lastWifiAttempt = millis();
  unsigned long lastBrokerAttempt = millis() - NETWORK_RETRY_INTERVAL_MS;
  bool shutdownStarted = false;
  unsigned long shutdownAt = 0;
  Message message{};
  Message pendingStatus{};
  bool hasPendingStatus = false;

  for (;;) {
    Diagnostic diagnostic{};
    if (xQueueReceive(diagnostics, &diagnostic, 0) == pdTRUE) {
      Serial.println(diagnostic.line);
    }
    const unsigned long now = millis();
    if (shutdownRequested.load()) {
      if (!shutdownStarted) {
        shutdownStarted = true;
        shutdownAt = now;
      }
      // Do not open a new connection during shutdown. A live broker ACKs the
      // retained offline publish before receiving DISCONNECT (R8).
      if (mqtt.connected() && mqtt.publish(kAvailabilityTopic, "offline", true, 1)) {
        mqtt.disconnect();
        break;
      }
      isConnected.store(false);
      if (!mqtt.connected() || millis() - shutdownAt >= NETWORK_SHUTDOWN_TIMEOUT_MS) {
        // No MQTT DISCONNECT when offline could not be acknowledged: allow
        // the broker to publish the registered offline Last Will instead.
        socket.stop();
        break;
      }
      vTaskDelay(pdMS_TO_TICKS(10));
      continue;
    }

#ifdef BENCH_AP
    if (!apReady && now - lastWifiAttempt >= NETWORK_RETRY_INTERVAL_MS) {
      lastWifiAttempt = now;
      apReady = startBenchAccessPoint();
    }
    if (now - lastPeerCheck >= kPeerCheckIntervalMs) {
      lastPeerCheck = now;
      IPAddress discovered;
      const bool found = apReady && benchBrokerAddress(discovered);
      if (!found || !peerReady || discovered != brokerAddress) {
        // Closing TCP without MQTT DISCONNECT lets the broker send the Last
        // Will on peer loss. This never calls or changes the feed controller.
        socket.stop();
        isConnected.store(false);
        if (found) {
          brokerAddress = discovered;
          mqtt.setHost(brokerAddress, MQTT_PORT);
          lastBrokerAttempt = now - NETWORK_RETRY_INTERVAL_MS;
        }
      }
      peerReady = found;
    }
    if (!peerReady) {
      vTaskDelay(pdMS_TO_TICKS(10));
      continue;
    }
#else
    if (WiFi.status() != WL_CONNECTED) {
      isConnected.store(false);
      socket.stop();
      if (now - lastWifiAttempt >= NETWORK_RETRY_INTERVAL_MS) {
        lastWifiAttempt = now;
        WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
      }
      vTaskDelay(pdMS_TO_TICKS(10));
      continue;
    }
#endif

    if (!mqtt.connected()) {
      isConnected.store(false);
      if (now - lastBrokerAttempt >= NETWORK_RETRY_INTERVAL_MS) {
        lastBrokerAttempt = now;
        replayRequired = false;
        // These operations can wait for TCP/MQTT acknowledgements, but run
        // exclusively here on core 0, away from the actuator loop on core 1.
#ifdef BENCH_AP
        const bool tcpConnected = socket.connect(brokerAddress, MQTT_PORT, NETWORK_COMMAND_TIMEOUT_MS);
#else
        const bool tcpConnected = socket.connect(MQTT_HOST, MQTT_PORT, NETWORK_COMMAND_TIMEOUT_MS);
#endif
        if (tcpConnected &&
            mqtt.connect(PUMP_ID, true) && mqtt.subscribe(kPrescriptionTopic, 1) &&
            mqtt.publish(kAvailabilityTopic, "online", true, 1)) {
          isConnected.store(true);
        } else {
          socket.stop();
        }
      }
    }

    if (mqtt.connected()) {
      mqtt.loop();
      if (mqtt.connected() && !replayRequired) {
        // Peek first: failed QoS 1 publications keep the front event for the
        // next connection. The main loop only appends to this queue.
        if (xQueuePeek(events, &message, 0) == pdTRUE &&
            mqtt.publish(kEventTopic, message.payload, message.length, false, 1)) {
          xQueueReceive(events, &message, 0);
        }
        // A one-item mailbox prevents stale telemetry from accumulating or
        // blocking events while the network is disconnected.
        if (xQueueReceive(status, &pendingStatus, 0) == pdTRUE) hasPendingStatus = true;
        if (mqtt.connected() && !replayRequired && hasPendingStatus &&
            mqtt.publish(kStatusTopic, pendingStatus.payload, pendingStatus.length, false, 0)) {
          hasPendingStatus = false;
        }
      }
    }
    if (mqtt.droppedMessages() != droppedCount) {
      droppedCount = mqtt.droppedMessages();
      queueMalformed();
      Serial.println("MQTT oversized prescription rejected");
    }
    if (replayRequired) {
      socket.stop();
      replayRequired = false;
    }
    isConnected.store(mqtt.connected());
    vTaskDelay(pdMS_TO_TICKS(10));
  }

  isConnected.store(false);
#ifdef BENCH_AP
  WiFi.softAPdisconnect(true);
#else
  WiFi.disconnect();
#endif
#endif
}

void networkTask(void*) {
  // Returning from runNetwork destroys the client and socket before this task
  // is deleted, including when shutdown does not restart the ESP32.
  runNetwork();
  if (restartRequested.load()) ESP.restart();
  vTaskDelete(nullptr);
}
}  // namespace

namespace mqtt_link {
void logLine(const char* line) {
  if (!started.load() || !line) return;
  Diagnostic diagnostic{};
  const size_t length = strnlen(line, sizeof(diagnostic.line));
  if (length >= sizeof(diagnostic.line)) return;
  memcpy(diagnostic.line, line, length + 1);
  xQueueSend(diagnostics, &diagnostic, 0);
}

bool begin() {
  if (started.load()) return !shutdownRequested.load();
  inbound = xQueueCreate(MQTT_INBOUND_QUEUE_LENGTH, sizeof(Message));
  events = xQueueCreate(MQTT_EVENT_QUEUE_LENGTH, sizeof(Message));
  status = xQueueCreate(1, sizeof(Message));
  diagnostics = xQueueCreate(8, sizeof(Diagnostic));
  if (inbound != nullptr && events != nullptr && status != nullptr && diagnostics != nullptr &&
      xTaskCreatePinnedToCore(networkTask, "pump-network", MQTT_TASK_STACK_SIZE,
                              nullptr, 1, nullptr, 0) == pdPASS) {
    started.store(true);
    return true;
  }
  if (inbound != nullptr) vQueueDelete(inbound);
  if (events != nullptr) vQueueDelete(events);
  if (status != nullptr) vQueueDelete(status);
  if (diagnostics != nullptr) vQueueDelete(diagnostics);
  inbound = events = status = diagnostics = nullptr;
  return false;
}

bool receivePrescription(char* buffer, size_t capacity, size_t* length) {
  if (!started.load() || buffer == nullptr) return false;
  Message message{};
  if (xQueuePeek(inbound, &message, 0) != pdTRUE || capacity <= message.length) return false;
  if (xQueueReceive(inbound, &message, 0) != pdTRUE) return false;
  memcpy(buffer, message.payload, message.length + 1);
  if (length != nullptr) *length = message.length;
  return true;
}

bool publishStatus(const char* json) {
  if (!started.load() || shutdownRequested.load()) return false;
  Message message{};
  return copyJson(message, json) && xQueueOverwrite(status, &message) == pdTRUE;
}

bool publishEvent(const char* json) {
  if (!started.load() || shutdownRequested.load()) return false;
  Message message{};
  return copyJson(message, json) && xQueueSend(events, &message, 0) == pdTRUE;
}

bool connected() { return isConnected.load(); }

void requestShutdown(bool restart) {
  if (!started.load()) return;
  if (restart) restartRequested.store(true);
  shutdownRequested.store(true);
}
}  // namespace mqtt_link
