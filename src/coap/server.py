"""
Module 1 Assignment — Task 2.1
CoAP Sensor Resource Server

Complete all TODO sections. The resource classes must match the
URIs and behaviours listed in the assignment spec.

Run with:  python -m src.coap.server
"""

import asyncio
import json
import logging
import random
from datetime import datetime, timezone

import aiocoap
import aiocoap.resource as resource
from aiocoap import Code, Message

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s")
log = logging.getLogger(__name__)

# ── Sensor simulation helpers ─────────────────────────────────────────────────

SENSOR_CONFIG = {
    "temperature": {"unit": "C",    "base": 70.0, "noise": 3.0},
    "vibration":   {"unit": "mm/s", "base": 1.2,  "noise": 0.3},
    "power":       {"unit": "kW",   "base": 45.0, "noise": 5.0},
}

def _sim(sensor: str) -> dict:
    cfg = SENSOR_CONFIG[sensor]
    return {
        "value": round(cfg["base"] + random.gauss(0, cfg["noise"]), 3),
        "unit":  cfg["unit"],
        "ts":    datetime.now(timezone.utc).isoformat(),
    }

def _json(data: dict) -> bytes:
    return json.dumps(data).encode()


# ── Observable Sensor Resource ────────────────────────────────────────────────

class SensorResource(resource.ObservableResource):
    """
    An observable CoAP resource that represents a single sensor on a line.

    TODO 1: Implement this class.
    Requirements:
      - Accept line and sensor_type in __init__
      - Store the current reading (initially simulated)
      - Start an asyncio background task (_update_loop) that:
          * Simulates a new reading every 5 seconds
          * Calls self.updated_state() to notify observers
      - Implement render_get:
          * Return a 2.05 Content response
          * Content-Format: 50 (application/json)
          * Payload: JSON-encoded current reading
    """

    def __init__(self, line: str, sensor_type: str):
        super().__init__()
        self.line        = line
        self.sensor_type = sensor_type
        self._reading    = _sim(sensor_type)
        # Start the background update loop
        asyncio.ensure_future(self._update_loop())

    async def _update_loop(self) -> None:
        """
        TODO 2: Every 5 seconds, simulate a new reading and notify observers.
        """
        while True:
            await asyncio.sleep(5)
            self._reading = _sim(self.sensor_type)
            log.debug(
                "Updated %s/%s: %s %s",
                self.line, self.sensor_type,
                self._reading["value"], self._reading["unit"],
            )
            self.updated_state()

    async def render_get(self, request: Message) -> Message:
        """
        TODO 3: Return the current sensor reading as a JSON response.
        Hint: use aiocoap.numbers.contentformat.ContentFormat.JSON (value 50)
              or pass content_format=50 to Message(...)
        """
        payload = _json(self._reading)
        return Message(
            code=Code.CONTENT,
            payload=payload,
            content_format=50,  # application/json
        )


# ── Non-Observable Sensor Resource (for /power) ───────────────────────────────

class PowerResource(resource.Resource):
    """
    A plain (non-observable) CoAP resource for the power sensor.
    The assignment spec lists /factory/line1/power as GET only (not Observable).
    """

    def __init__(self, line: str):
        super().__init__()
        self.line    = line
        self._reading = _sim("power")
        asyncio.ensure_future(self._update_loop())

    async def _update_loop(self) -> None:
        while True:
            await asyncio.sleep(5)
            self._reading = _sim("power")

    async def render_get(self, request: Message) -> Message:
        payload = _json(self._reading)
        return Message(
            code=Code.CONTENT,
            payload=payload,
            content_format=50,
        )


# ── Actuator Resource ─────────────────────────────────────────────────────────

class ActuatorResource(resource.Resource):
    """
    A CoAP resource representing a controllable fan actuator.

    TODO 4: Implement this class.
    Requirements:
      - Track state: "OFF" initially
      - render_get: return current state as JSON {"state": "ON"|"OFF"}
      - render_put: accept {"state": "ON"} or {"state": "OFF"}
          * Update internal state
          * Return 2.04 Changed on success
          * Return 4.00 Bad Request if payload is malformed or state is invalid
    """

    def __init__(self):
        super().__init__()
        self._state = "OFF"

    async def render_get(self, request: Message) -> Message:
        """TODO 5: Return current fan state as JSON."""
        payload = _json({"state": self._state})
        return Message(
            code=Code.CONTENT,
            payload=payload,
            content_format=50,
        )

    async def render_put(self, request: Message) -> Message:
        """TODO 6: Accept ON/OFF command and update state."""
        try:
            data = json.loads(request.payload.decode("utf-8"))
            new_state = data.get("state", "").upper()
            if new_state not in ("ON", "OFF"):
                raise ValueError(f"Invalid state: {new_state!r}")
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
            log.warning("ActuatorResource bad request: %s", exc)
            return Message(code=Code.BAD_REQUEST, payload=str(exc).encode())

        self._state = new_state
        log.info("Fan actuator set to %s", self._state)
        return Message(code=Code.CHANGED)


# ── Block-wise Manifest Resource ──────────────────────────────────────────────

class ManifestResource(resource.Resource):
    """
    A large resource that triggers CoAP Block2 transfer.

    TODO 7: Implement this class.
    Requirements:
      - render_get must return a payload of AT LEAST 3072 bytes (3 KB)
      - Content-Format: 50 (application/json)
      - The payload should be a realistic-looking firmware manifest
        (list of sensor firmware versions, checksums, update URLs, etc.)
      - aiocoap handles Block2 fragmentation automatically if the payload
        exceeds the negotiated block size — you just need to return the full payload
    """

    # Build the manifest once at class level so every GET returns the same data
    _MANIFEST = None

    @classmethod
    def _build_manifest(cls) -> bytes:
        if cls._MANIFEST is not None:
            return cls._MANIFEST

        sensor_types = ["temperature", "vibration", "power", "humidity", "pressure",
                        "flow", "level", "current", "voltage", "rpm"]
        lines = ["line1", "line2"]
        vendors = ["SmartSense GmbH", "IndustrialEdge Ltd", "SensorCorp", "IoTech Inc"]
        channels = ["stable", "beta", "lts"]

        entries = []
        seq = 0
        for _ in range(60):           # 60 entries ≫ ensures > 3 KB
            seq += 1
            stype  = sensor_types[seq % len(sensor_types)]
            line   = lines[seq % len(lines)]
            vmaj   = 2 + (seq % 3)
            vmin   = seq % 10
            vpatch = (seq * 7) % 20
            vendor = vendors[seq % len(vendors)]
            chan   = channels[seq % len(channels)]
            entry = {
                "id": f"fw-{line}-{stype}-{seq:04d}",
                "line": line,
                "sensor_type": stype,
                "vendor": vendor,
                "version": f"{vmaj}.{vmin}.{vpatch}",
                "channel": chan,
                "released": f"2025-{(seq % 12) + 1:02d}-{(seq % 28) + 1:02d}T00:00:00Z",
                "size_bytes": 65536 + seq * 512,
                "sha256": f"{'a1b2c3d4e5f6' * 2}{seq:08x}"[:64],
                "url": (
                    f"https://firmware.smartfactory.io/releases/{chan}/"
                    f"{stype}/{vmaj}.{vmin}.{vpatch}/fw-{stype}-{seq:04d}.bin"
                ),
                "signature": f"{'deadbeef' * 8}{seq:016x}"[:128],
                "min_hw_rev": f"r{(seq % 5) + 1}",
                "notes": (
                    f"Firmware {vmaj}.{vmin}.{vpatch} for {stype} sensors on {line}. "
                    f"Vendor: {vendor}. Channel: {chan}. "
                    "Includes improved noise filtering, extended self-test routines, "
                    "and watchdog timer hardening for reliable operation in high-vibration environments."
                ),
            }
            entries.append(entry)

        manifest = {
            "manifest_version": "2.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "generator": "SmartFactory Firmware Distribution Service",
            "facility": "SmartFactory Inc — Main Plant",
            "total_entries": len(entries),
            "schema": "https://firmware.smartfactory.io/schema/manifest-v2.json",
            "entries": entries,
        }

        cls._MANIFEST = json.dumps(manifest, indent=2).encode("utf-8")
        return cls._MANIFEST

    async def render_get(self, request: Message) -> Message:
        """TODO 8: Return a >= 3 KB JSON firmware manifest."""
        payload = self._build_manifest()
        assert len(payload) >= 3072, (
            f"Manifest payload is only {len(payload)} bytes — must be >= 3072"
        )
        log.info("Serving manifest: %d bytes", len(payload))
        return Message(
            code=Code.CONTENT,
            payload=payload,
            content_format=50,
        )


# ── Resource Tree & Server Setup ──────────────────────────────────────────────

async def build_server() -> aiocoap.Context:
    """
    TODO 9: Build the CoAP resource tree and create the server context.

    Register resources at these paths (use colon-separated path segments):
      factory/line1/temperature  → SensorResource("line1", "temperature")
      factory/line1/vibration    → SensorResource("line1", "vibration")
      factory/line1/power        → SensorResource("line1", "power")
      factory/line2/temperature  → SensorResource("line2", "temperature")
      actuator/line1/fan         → ActuatorResource()
      factory/manifest           → ManifestResource()

    Also add a /.well-known/core resource listing using resource.WKCResource.

    Return the created aiocoap.Context.
    """
    root = resource.Site()

    # Sensor resources for line 1
    root.add_resource(["factory", "line1", "temperature"],
                      SensorResource("line1", "temperature"))
    root.add_resource(["factory", "line1", "vibration"],
                      SensorResource("line1", "vibration"))
    # /factory/line1/power is GET only (not Observable per assignment spec)
    root.add_resource(["factory", "line1", "power"],
                      PowerResource("line1"))

    # Sensor resources for line 2
    root.add_resource(["factory", "line2", "temperature"],
                      SensorResource("line2", "temperature"))

    # Actuator resource
    root.add_resource(["actuator", "line1", "fan"],
                      ActuatorResource())

    # Block2 manifest resource
    root.add_resource(["factory", "manifest"],
                      ManifestResource())

    # Well-known resource listing
    root.add_resource([".well-known", "core"],
                      resource.WKCResource(root.get_resources_as_linkheader))

    # Use 'localhost' string as bind address so it resolves consistently with
    # test URIs that use coap://localhost. On Windows, passing None fails because
    # aiocoap tries to bind to IPv6 :: which is not always available.
    try:
        context = await aiocoap.Context.create_server_context(root, bind=("localhost", 5683))
    except Exception:
        context = await aiocoap.Context.create_server_context(root, bind=("127.0.0.1", 5683))
    return context


async def main() -> None:
    context = await build_server()
    log.info("CoAP server running on coap://localhost:5683")
    log.info("Resources: /factory/line{1,2}/{temperature,vibration,power}, /actuator/line1/fan, /factory/manifest")
    await asyncio.get_event_loop().create_future()  # run forever


if __name__ == "__main__":
    asyncio.run(main())
