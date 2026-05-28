"""
Module 1 Assignment — Task 1.2
MQTT Wildcard Subscriber

Complete all TODO sections. Do not modify the function signatures.
"""

import json
import logging
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

import paho.mqtt.client as mqtt

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────
BROKER_HOST  = "localhost"
BROKER_PORT  = 1883
CLIENT_ID    = "smartfactory-subscriber-001"

TOPIC_ALL        = "factory/#"              # all factory messages
TOPIC_TEMP       = "factory/+/temperature"  # all temperature readings (any line)

CRITICAL_TEMP    = 85.0
SUMMARY_INTERVAL = 30   # seconds


class SmartFactorySubscriber:
    """Subscribes to SmartFactory sensor topics and processes incoming data."""

    def __init__(self, broker_host: str = BROKER_HOST, broker_port: int = BROKER_PORT):
        self.broker_host  = broker_host
        self.broker_port  = broker_port
        self._client      = mqtt.Client(client_id=CLIENT_ID, clean_session=False)
        self._msg_counts: dict[str, int] = defaultdict(int)
        self._last_summary = time.time()
        self._alerts_fired = 0

        self._client.on_connect = self.on_connect
        self._client.on_message = self.on_message

    # ── Connection ─────────────────────────────────────────────────────────────

    def on_connect(self, client, userdata, flags: dict, rc: int) -> None:
        """
        TODO 1: On successful connect (rc == 0):
          - Log "Connected to broker"
          - Subscribe to TOPIC_ALL at QoS 1
          - Subscribe to TOPIC_TEMP at QoS 2  (separate subscription)
          Log any connection failure at ERROR level.
        """
        if rc == 0:
            log.info("Connected to broker")
            client.subscribe(TOPIC_ALL, qos=1)
            client.subscribe(TOPIC_TEMP, qos=2)
        else:
            log.error("Connection failed with rc=%d", rc)

    # ── Message Handling ───────────────────────────────────────────────────────

    def on_message(self, client, userdata, msg: mqtt.MQTTMessage) -> None:
        """
        TODO 2: Handle every incoming message.
          - Increment self._msg_counts[msg.topic]
          - Attempt to parse msg.payload as JSON; fall back to raw string
          - Call _print_message to display the message
          - If the topic ends with '/temperature', call _check_temperature_alert
          - Every SUMMARY_INTERVAL seconds, call _print_summary
        """
        self._msg_counts[msg.topic] += 1

        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            payload = msg.payload.decode("utf-8", errors="replace")

        self._print_message(msg, payload)

        if msg.topic.endswith("/temperature"):
            self._check_temperature_alert(msg.topic, payload)

        now = time.time()
        if now - self._last_summary >= SUMMARY_INTERVAL:
            self._print_summary()
            self._last_summary = now

    def _print_message(self, msg: mqtt.MQTTMessage, payload: Any) -> None:
        """
        TODO 3: Print a formatted message line:
          Format: [HH:MM:SS] {topic}  val={value_or_payload}  QoS={qos}  retain={retain}
          - If payload is a dict with key "value", show that value with unit if present
          - Otherwise show the raw payload
        """
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        if isinstance(payload, dict) and "value" in payload:
            unit = payload.get("unit", "")
            val_str = f"{payload['value']} {unit}".strip()
        else:
            val_str = str(payload)

        print(
            f"[{ts}] {msg.topic}  val={val_str}  QoS={msg.qos}  retain={bool(msg.retain)}"
        )

    def _check_temperature_alert(self, topic: str, payload: Any) -> None:
        """
        TODO 4: Check if a temperature reading is critical.
          - If payload is a dict and payload["value"] > CRITICAL_TEMP:
              - Increment self._alerts_fired
              - Print:
                  ╔══════════════════════════════════════╗
                  ║  ⚠ CRITICAL ALERT — {topic}
                  ║  Temperature: {value}°C  (threshold: {CRITICAL_TEMP}°C)
                  ║  Time: {timestamp from payload or now}
                  ╚══════════════════════════════════════╝
        """
        if isinstance(payload, dict) and payload.get("value", 0) > CRITICAL_TEMP:
            self._alerts_fired += 1
            ts = payload.get("timestamp", datetime.now(timezone.utc).isoformat())
            value = payload["value"]
            print("╔══════════════════════════════════════╗")
            print(f"║  ⚠ CRITICAL ALERT — {topic}")
            print(f"║  Temperature: {value}°C  (threshold: {CRITICAL_TEMP}°C)")
            print(f"║  Time: {ts}")
            print("╚══════════════════════════════════════╝")

    def _print_summary(self) -> None:
        """
        TODO 5: Print a summary of messages received per topic.
          Format:
            ── Message Summary ──────────────────────
            {topic:<50}  {count:>6} msgs
            ...
            Total: {sum} messages  |  Alerts fired: {self._alerts_fired}
            ─────────────────────────────────────────
        """
        print("── Message Summary ──────────────────────")
        total = 0
        for topic, count in sorted(self._msg_counts.items()):
            print(f"  {topic:<50}  {count:>6} msgs")
            total += count
        print(f"  Total: {total} messages  |  Alerts fired: {self._alerts_fired}")
        print("─────────────────────────────────────────")

    # ── Run ────────────────────────────────────────────────────────────────────

    def run(self) -> None:
        """Connect and block until interrupted."""
        self._client.connect(self.broker_host, self.broker_port, keepalive=60)
        log.info("Listening for messages (Ctrl-C to stop)")
        try:
            self._client.loop_forever()
        except KeyboardInterrupt:
            log.info("Subscriber stopped")
        finally:
            self._client.disconnect()


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    sub = SmartFactorySubscriber()
    sub.run()
