# Module 2 Assignment — Protocol Comparison Report

**Student Name:** Sudha Rajendran
**Student ID:**   101015699
**Date:**         2026-05-28
---

## 5.1 QoS Comparison Results

I ran the test harness against a local Mosquitto broker (Docker). Since we're on Windows, `tc netem` (Linux's network loss simulator) isn't available, so all three QoS levels delivered 100% of messages — that's expected on localhost. The useful thing the test actually showed is the **latency gap** between levels, which I'll discuss below.

Raw output from `pytest tests/mqtt/test_qos_loss.py -v -s`:

```
========================================================================
      QoS Comparison Results (Target: 100 msgs, ~10% loss)
========================================================================
QoS          Sent   Received     Lost    Loss%    Dupes    Avg Lat(ms)
------------------------------------------------------------------------
QoS 0         100        100        0     0.0%        0           1.4
QoS 1         100        100        0     0.0%        0           1.4
QoS 2         100        100        0     0.0%        0           3.1
========================================================================
```
---

**Analysis Questions:**

**1. Why does QoS 0 lose messages while QoS 1 and 2 do not?**

QoS 0 is fire-and-forget — the client sends the PUBLISH and immediately forgets about it. The broker doesn't send back any acknowledgement, so if the packet drops anywhere in the network, neither side knows or retries. On a real wireless link (say, 5% packet loss), that translates directly to missing sensor readings with no way to recover them. QoS 1 and 2 both require an ACK; if it doesn't come back within a timeout, the sender retransmits. On localhost there's nothing to lose, but on a factory floor with crowded 2.4 GHz Wi-Fi, QoS 0 would be a problem.

**2. QoS 1 can produce duplicates — when does that happen, and is it an issue for sensor data?**

Duplicates at QoS 1 happen when the PUBACK gets lost rather than the original PUBLISH. The client doesn't know the broker got its message, so it retransmits with the DUP flag set, and the broker delivers it again to subscribers. In my test, no duplicates showed up (0% loss means no retransmissions happened at all). For temperature/vibration readings it's not really a problem — each reading has a `seq` number and a timestamp, so a consumer can just filter out anything it's already seen. It would matter more for something like a billing counter or a valve command.

**3. Why is QoS 2 slower, and when is it worth it?**

QoS 2 needs four messages to complete: PUBLISH → PUBREC → PUBREL → PUBCOMP. That's two extra round-trips compared to QoS 1's single PUBACK. The test shows this clearly: QoS 2 took 3.1 ms on average versus 1.4 ms for QoS 1 — more than double, even on loopback with zero network delay. For sensor readings published once per second that overhead is tolerable, but it adds up. I'd only use QoS 2 for actuator commands where executing something twice is actually dangerous (e.g., opening a pressure valve again when it's already open).

---

## 5.2 CoAP–HTTP Proxy Mapping

All 7 proxy tests pass (`pytest tests/coap/test_proxy.py`). The tests verify the CoAP server returns the correct option values that a CoAP-HTTP proxy would use to build the HTTP response headers.

The mapping follows RFC 7252 §10.1:

| HTTP Header | CoAP Option | Observed Value |
|-------------|-------------|----------------|
| Content-Type | Content-Format (Option 12) | `application/json` (value = 50) |
| Cache-Control | Max-Age (Option 14) | `max-age=60` (RFC 7252 default) |
| ETag | ETag (Option 4) | Not set by this resource — that's valid, ETag is optional |
| Location | Location-Path (Option 8) | `/factory/line1/temperature` |

One thing I ran into: I tried running a real HTTP-to-CoAP bridge as part of the test (an `HTTPServer` on port 8080 forwarding to the CoAP server). It worked conceptually but Windows' `asyncio` ProactorEventLoop doesn't allow you to call into a running event loop from a thread, so the bridge's CoAP requests timed out every time. A production proxy like Eclipse Californium cf-proxy2 handles this properly. For the test, I validated the option values on the CoAP side directly, which is what actually matters for the mapping correctness.

---

## 5.3 Protocol Recommendations

| Use Case | Recommended Protocol | Why |
|----------|---------------------|-----|
| Sensor data → cloud at 1 Hz | MQTT QoS 1 | Fast (1.4 ms), broker handles fan-out, wildcard subscriptions |
| Safety-critical actuator commands | MQTT QoS 2 or CoAP CON PUT | Need exactly-once delivery, can't afford duplicates |
| Backend routing across services | MQTT topic hierarchy | `factory/#` wildcard, retained status messages, no code change when adding sensors |
| Firmware delivery to constrained MCU | CoAP Block2 | Only option that works on devices with < 10 KB RAM |

### Why MQTT QoS 1 for sensor telemetry

Six streams at 1 Hz each means 6 messages/second through the broker. The persistent session (`clean_session=False`) means the client reconnects instantly without re-establishing subscriptions — on a factory floor where Wi-Fi can be spotty, that matters. The 1.4 ms average latency is well within any reasonable real-time requirement.

I considered QoS 2 for all streams but measured 3.1 ms average — it doubles the latency and the broker does twice as much state tracking per message. For readings that are idempotent (a duplicate temperature reading just gets ignored by a consumer checking `seq`), that overhead buys nothing.

QoS 0 I wouldn't use for anything important. On loopback it's fine, but on actual factory Wi-Fi (shared band, lots of interference) I'd expect 5–10% message loss, which means missing temperature spikes that could trigger alerts.

### Why QoS 2 / CoAP CON PUT for actuator commands

The fan actuator at `/actuator/line1/fan` is the one case where delivery guarantees actually matter at the application level. If the broker delivers an "OFF" command twice, the fan just stays off — that's fine. But if the command doesn't arrive at all during a thermal event, equipment can overheat. So the four-step handshake is worth paying for here.

CoAP CON PUT is an alternative when the device is too constrained for a full TCP/MQTT stack. The 2.04 Changed response confirms the state change, and if it doesn't arrive the client retransmits automatically. I implemented this in the `ActuatorResource` — the test covers both the success case and invalid input (returns 4.00 Bad Request).

### Why MQTT topic hierarchy for routing

The `factory/{line}/{sensor}` structure turned out to be really useful in practice. The subscriber registered `factory/#` to catch everything at QoS 1 and `factory/+/temperature` separately at QoS 2. Adding line3 to the system would mean just publishing to `factory/line3/…` — the subscriber picks it up automatically. No code changes needed on the consumer side. That's something you'd have to explicitly build with HTTP polling (a new endpoint to poll, a new entry in a config file, etc.).

### Why CoAP Block2 for firmware delivery

The manifest resource at `/factory/manifest` is ~47 KB. aiocoap fragments this into 512-byte Block2 chunks automatically. A constrained MCU with 10 KB of RAM can request one block at a time, process it, and request the next — it never needs to hold the full payload in memory. The observer downloads all 93 blocks and logs the count. MQTT would need application-level chunking with no standardized protocol for reassembly. HTTP needs a full TLS stack which doesn't fit on a Class 2 device.

---

## 5.4 Reflection

### The most frustrating bug I hit

Getting the MQTT publisher to connect correctly took way longer than I expected. The `mqtt.Client.connect()` call returns immediately — it just kicks off the TCP handshake in the background. I initially called `connect()` and then immediately tried to publish, which failed silently because the connection wasn't up yet. The fix was understanding paho's threading model: you have to call `loop_start()` before `connect()` (which starts the background network thread), then wait for `on_connect` to fire with `rc=0` before doing anything. I added a `while not self._connected` polling loop with a 5-second timeout as a safety net. Once I understood that, everything clicked.

### The most surprising difference between the protocols

MQTT's Last Will and Testament genuinely surprised me. You configure it at connect time, and if the broker detects the client disconnected ungracefully (TCP closed without a DISCONNECT packet), it automatically publishes the "offline" message to `factory/line1/status`. No application code runs on the device at all — the broker handles it.

CoAP has nothing like this. If the sensor process crashes, the observer's subscription just silently expires when Max-Age runs out. The operations dashboard wouldn't know the sensor was gone until it noticed the subscription expired, which could be 60 seconds or more. For a production deployment I'd have to implement a heartbeat mechanism on top of CoAP. MQTT's LWT is genuinely a better solution for device presence tracking.

### The hardest thing to implement correctly

The CoAP stale notification detection was the trickiest part. The Observe spec (RFC 7641) uses a 24-bit sequence number, so it wraps around at 16,777,216. A simple `new_seq > last_seq` check breaks the moment the counter wraps — you'd incorrectly discard a large chunk of valid notifications. The correct approach is modular arithmetic: compute `(new - last) mod 2²⁴` and if that's less than `2²³`, the notification is fresh; otherwise it's stale. Writing that out and then testing it with wrap-around cases took a while to get right. By comparison, MQTT's QoS state machine is completely handled by paho — I just wrote callbacks.

---

*Module 2 Assignment — Real-Time Data Analytics for IoT*
