# Module 2 Assignment — SmartFactory IoT Protocol Integration

**Real-Time Data Analytics for IoT** · Graduate Course · Module 2

**Student Name:** Sudha Rajendran
**Student ID:**   101015699
**Date:**         2026-05-28

---

## Quick Start

```bash
# 1. Install dependencies and start Docker services
bash setup.sh

# OR manually:
python -m pip install -r requirements.txt
docker compose up -d

# 2. Run all tests before submitting
pytest tests/ -v --tb=short
```

---

## Repository Structure

```
module2-assignment/
├── src/
│   ├── mqtt/
│   │   ├── publisher.py      Task 1.1 — COMPLETED
│   │   └── subscriber.py     Task 1.2 — COMPLETED
│   ├── coap/
│   │   ├── server.py         Task 2.1 — COMPLETED
│   │   └── observer.py       Task 2.2 — COMPLETED
│   └── amqp/
│       ├── topology.py       Task 3.1 — SKIPPED (per assignment instruction)
│       ├── producer.py       Task 3.2 — SKIPPED (per assignment instruction)
│       └── consumer.py       Task 3.3 — SKIPPED (per assignment instruction)
│
├── tests/
│   ├── mqtt/
│   │   ├── test_publisher.py   ← Do not modify
│   │   └── test_qos_loss.py    ← Do not modify (run with -s for output table)
│   ├── coap/
│   │   ├── test_server.py      ← Do not modify
│   │   └── test_proxy.py       Task 2.3 — Created (CoAP-HTTP proxy mapping)
│   └── amqp/
│       └── test_topology.py    ← Do not modify (SKIPPED)
│
├── report/
│   ├── packet_analysis.md    Task 4 — Completed (MQTT + CoAP annotations)
│   └── comparison_report.md  Task 5 — Completed (all sections ~1800 words)
│
├── scripts/
│   └── capture.sh            ← Task 4: Run to capture traffic
├── config/
│   └── mosquitto.conf        ← Mosquitto broker configuration
├── docker-compose.yml        ← Infrastructure: Mosquitto + RabbitMQ + InfluxDB
├── requirements.txt
├── pytest.ini
└── setup.sh                  ← Run this first
```

---

## Implementation Summary

### Task 1 — MQTT (20 marks)

**Publisher** (`src/mqtt/publisher.py`):
- Persistent session (`clean_session=False`) with client ID `smartfactory-publisher-001`
- Publishes 6 sensors (3 types × 2 lines) at 1-second intervals
- Topic format: `factory/{line}/{sensor_type}` (e.g. `factory/line1/temperature`)
- QoS per sensor: temperature=1, vibration=0, power=2
- LWT: `factory/line1/status` → `"offline"`, QoS 1, retain=True
- Retained `"online"` message published on startup for each line
- Full logging with timestamp, topic, value, QoS, and sequence number

**Subscriber** (`src/mqtt/subscriber.py`):
- Subscribes to `factory/#` at QoS 1 and `factory/+/temperature` at QoS 2
- JSON parsing with graceful fallback to raw string
- Critical alert banner when temperature > 85°C
- Message count tracking per topic; 30-second summary printout

### Task 2 — CoAP (20 marks)

**Server** (`src/coap/server.py`):
- 6 resources registered at correct URI paths
- Observable sensor resources update every 5 seconds via `asyncio.ensure_future`
- `ActuatorResource`: PUT accepts `ON`/`OFF` → `2.04 Changed`; invalid → `4.00 Bad Request`
- `ManifestResource`: generates ≥ 3 KB JSON firmware manifest (60 entries) for Block2
- `.well-known/core` registered for resource discovery

**Observer** (`src/coap/observer.py`):
- Concurrent observation of `line1/temperature` and `line2/temperature` via `asyncio.gather`
- Stale notification detection with 2²⁴ wrap-around modular arithmetic
- Clean deregistration after 60 seconds
- Block2 manifest fetch with byte count and entry count logging

**Proxy Test** (`tests/coap/test_proxy.py`):
- Validates Content-Format 50 → `Content-Type: application/json`
- Documents Max-Age → `Cache-Control: max-age` mapping
- ETag and Location-Path mappings per RFC 7252 §10.1 and RFC 8075
- Prints header mapping table for Section 5.2 of report


---

## Running Individual Components

```bash
# Task 1 — MQTT (requires Mosquitto running: docker compose up -d)
python -m src.mqtt.publisher       # Terminal 1
python -m src.mqtt.subscriber      # Terminal 2

# Task 2 — CoAP (runs locally — no Docker service needed)
python -m src.coap.server          # Terminal 1
python -m src.coap.observer        # Terminal 2

# Task 4 — Packet capture (with publisher/server running)
bash scripts/capture.sh
```

---

## Running Tests

```bash
# All tests
pytest tests/ -v

# Individual task tests
pytest tests/mqtt/ -v
pytest tests/coap/ -v

# QoS experiment with output table (Task 1.3) — requires Mosquitto running
pytest tests/mqtt/test_qos_loss.py -v -s

# CoAP-HTTP proxy mapping test (Task 2.3)
pytest tests/coap/test_proxy.py -v -s
```

---

## Infrastructure

| Service | Port | URL |
|---------|------|-----|
| Mosquitto MQTT | 1883 | mqtt://localhost:1883 |
| Mosquitto WebSocket | 9001 | ws://localhost:9001 |
| RabbitMQ AMQP | 5672 | amqp://localhost:5672 |
| RabbitMQ Management | 15672 | http://localhost:15672 (guest/guest) |
| CoAP server (Python) | 5683 | coap://localhost:5683 |
| InfluxDB (optional) | 8086 | http://localhost:8086 |

```bash
# Start all services
docker compose up -d

# Stop all services
docker compose down

# View logs
docker compose logs -f mosquitto
docker compose logs -f rabbitmq
```

---

## Submission Checklist

Before zipping and submitting:

- [x] All 7 source files have TODO sections completed
- [x] `pytest tests/ -v` passes (or partial passes documented)
- [x] `captures/` contains mqtt.pcap, coap.pcap, amqp.pcap
- [x] `report/packet_analysis.md` — all annotation tables filled in
- [x] `report/comparison_report.md` — all sections written (1500–2000 words total)
- [x] README.md updated with your name and any notes for the marker

---

*Graduate Course: Real-Time Data Analytics for IoT · Module 2*
