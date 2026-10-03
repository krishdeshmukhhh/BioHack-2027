"""MQTT bridge. paho runs its network loop in its own thread; everything it
receives is handed to the asyncio loop with call_soon_threadsafe (R5).
"""

import asyncio
import logging

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

log = logging.getLogger("hub.mqtt")

# Topics from shared/protocol/topics.md. Subscribers use QoS 1; pumps publish at QoS 0.
SUBSCRIPTIONS = [("pump/+/status", 1), ("pump/+/event", 1), ("pump/+/availability", 1)]
CONNECTED = "$hub/connected"  # internal marker put on the queue after each (re)connect


class MqttBridge:
    def __init__(self, host: str, port: int, client_id: str = "smart-pump-hub") -> None:
        self.host = host
        self.port = port
        self._loop: asyncio.AbstractEventLoop | None = None
        self._queue: asyncio.Queue[tuple[str, bytes]] | None = None
        self._client = mqtt.Client(CallbackAPIVersion.VERSION2, client_id=client_id)
        self._client.reconnect_delay_set(min_delay=1, max_delay=10)
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message

    def start(self, loop: asyncio.AbstractEventLoop, queue: asyncio.Queue) -> None:
        self._loop = loop
        self._queue = queue
        self._client.connect_async(self.host, self.port, keepalive=30)
        self._client.loop_start()  # reconnects in the background

    def stop(self) -> None:
        self._client.disconnect()
        self._client.loop_stop()

    def publish(self, topic: str, payload: str, qos: int, retain: bool) -> bool:
        info = self._client.publish(topic, payload, qos=qos, retain=retain)
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            log.warning("publish to %s failed: %s", topic, mqtt.error_string(info.rc))
            return False
        return True

    # paho thread below this line

    def _handoff(self, topic: str, payload: bytes) -> None:
        assert self._loop is not None and self._queue is not None
        self._loop.call_soon_threadsafe(self._queue.put_nowait, (topic, payload))

    def _on_connect(self, client, userdata, flags, reason_code, properties) -> None:
        if reason_code.is_failure:
            log.warning("broker refused connection: %s", reason_code)
            return
        log.info("connected to broker %s:%s", self.host, self.port)
        # Subscribing here means subscriptions come back after every reconnect.
        client.subscribe(SUBSCRIPTIONS)
        self._handoff(CONNECTED, b"")

    def _on_disconnect(self, client, userdata, flags, reason_code, properties) -> None:
        log.warning("disconnected from broker: %s", reason_code)

    def _on_message(self, client, userdata, msg: mqtt.MQTTMessage) -> None:
        self._handoff(msg.topic, msg.payload)
