# Module 2 Assignment — Packet Analysis
## Task 4: Wire-Level Protocol Annotation
**Student Name:** Sudha Rajendran
**Student ID:**   101015699
**Date:**         2026-05-28


---

## 4.2 MQTT Packet Annotations

### CONNECT Packet

When the publisher calls `connect()`, this is the first packet sent to Mosquitto. It carries all the session setup: client ID, credentials, LWT configuration, and the `clean_session` flag.

| Field | Offset (bytes) | Raw Hex | Decoded Value |
|-------|---------------|---------|---------------|
| Fixed header byte 1 | 0 | `10` | Packet type = CONNECT (0001), flags = 0000 |
| Remaining length | 1 | `3F` | 63 bytes follow |
| Protocol name length | 2–3 | `00 04` | 4 |
| Protocol name | 4–7 | `4D 51 54 54` | "MQTT" |
| Protocol version | 8 | `04` | 4 → MQTT 3.1.1 |
| Connect flags | 9 | `C4` | see below |
| Keep-alive | 10–11 | `00 3C` | 60 seconds |
| Client ID length | 12–13 | `00 1B` | 27 |
| Client ID | 14–… | `73 6D 61 72 74 …` | "smartfactory-publisher-001" |

**Connect flags byte 0xC4 = 1100 0100:**

| Bit | Name | Value | What it means |
|-----|------|-------|---------------|
| 7 | Username flag | 1 | Username included |
| 6 | Password flag | 1 | Password included |
| 5 | Will retain | 0 | LWT message not retained |
| 4–3 | Will QoS | 01 | LWT delivered at QoS 1 |
| 2 | Will flag | 1 | LWT is configured |
| 1 | Clean session | 0 | Persistent session — broker keeps state across reconnects |
| 0 | Reserved | 0 | — |

The important one here is bit 1. Because `clean_session=False`, the broker will hold any queued messages and preserve subscriptions if the client disconnects and comes back with the same client ID. That's what makes the persistent session work. If this bit were 1, the broker would wipe everything on disconnect.

---

### QoS 1 PUBLISH Packet

This is what goes on the wire when the publisher sends a temperature reading. The payload is JSON — I can see `7B` (opening `{`) at the start.

| Field | Offset (bytes) | Raw Hex | Decoded Value |
|-------|---------------|---------|---------------|
| Fixed header byte 1 | 0 | `32` | Type=PUBLISH, DUP=0, QoS=1, RETAIN=0 |
| Remaining length | 1 | `6E` | 110 bytes |
| Topic length | 2–3 | `00 18` | 24 |
| Topic string | 4–27 | `66 61 63 74 6F 72 79 …` | "factory/line1/temperature" |
| Packet Identifier | 28–29 | `00 01` | 1 |
| Payload | 30–… | `7B 22 6C 69 6E 65 …` | `{"line":"line1","sensor":"temperature","value":71.452,...}` |

**Header byte 0x32 = 0011 0010:**

| Bits 7–4 | Bit 3 (DUP) | Bits 2–1 (QoS) | Bit 0 (RETAIN) |
|----------|-------------|----------------|----------------|
| 0011 = PUBLISH | 0 = original, not a retransmit | 01 = QoS 1 | 0 = not retained |

The Packet Identifier (0x0001) is what the broker echoes back in the PUBACK. Our publisher uses this to confirm which message was acknowledged.

---

### PUBACK Packet

After the broker delivers the PUBLISH to its internal queue, it sends back this tiny 4-byte packet:

| Field | Offset | Raw Hex | Decoded Value |
|-------|--------|---------|---------------|
| Fixed header | 0 | `40` | Type = PUBACK (0100), flags = 0000 |
| Remaining length | 1 | `02` | 2 bytes |
| Packet Identifier | 2–3 | `00 01` | 1 |

**Packet Identifier match: PUBLISH = 1 → PUBACK = 1 ✓**

This matching ID is the entire QoS 1 reliability mechanism. The publisher keeps the message in an in-flight buffer until it sees a PUBACK with the matching ID, then removes it. If the PUBACK never arrives (packet loss), the publisher retransmits the PUBLISH with DUP=1.

---

### QoS 2 Four-Step Handshake

The power sensor (`factory/line1/power`) uses QoS 2. This is what the exchange looks like:

| Step | Packet | Direction | Packet ID | Fixed Header |
|------|--------|-----------|-----------|-------------|
| 1 | PUBLISH | Client → Broker | 2 | `34` (QoS bits = 10) |
| 2 | PUBREC  | Broker → Client | 2 | `50` |
| 3 | PUBREL  | Client → Broker | 2 | `62` |
| 4 | PUBCOMP | Broker → Client | 2 | `70` |

The broker only delivers the message to subscribers after step 4. Steps 2 and 3 are the "exactly-once" mechanism — PUBREC tells the client "I got it, stop sending", PUBREL tells the broker "okay you can deliver it now". That's why QoS 2 is 3.1 ms vs 1.4 ms for QoS 1 in the test — two extra round-trips on top.

---

## 4.3 CoAP Packet Annotations

### CON GET Request to `/factory/line1/temperature`

```
41 01  AB CD  EF  B4 66 61 63 74 6F 72 79  04 6C 69 6E 65 31  0B 74 65 6D 70 65 72 61 74 75 72 65
[Hdr0][Code][MsgID ][Tok][ Uri-Path: "factory" (7 bytes) ][ "line1" (5) ][ "temperature" (11) ]
```

| Field | Bits | Raw | Decoded |
|-------|------|-----|---------|
| Version (bits 7–6) | 2 | `01` | Always 1 |
| Type (bits 5–4) | 2 | `00` | CON — must be acknowledged |
| Token Length (bits 3–0) | 4 | `0001` | 1 byte token |
| Code | 8 | `01` | 0.01 = GET |
| Message ID | 16 | `AB CD` | 43981 — matched against ACK |
| Token | 8 | `EF` | 0xEF — matched against response |
| Uri-Path "factory" | — | `B4 66…79` | Delta=11 (Uri-Path), len=7, value="factory" |
| Uri-Path "line1" | — | `04 6C…31` | Delta=0 (same option), len=5, value="line1" |
| Uri-Path "temperature" | — | `0B 74…65` | Delta=0, len=11, value="temperature" |

**Byte 0 breakdown (0x41 = 0100 0001):**

| Bit 7 | Bit 6 | Bit 5 | Bit 4 | Bit 3 | Bit 2 | Bit 1 | Bit 0 |
|-------|-------|-------|-------|-------|-------|-------|-------|
| Ver=0 | Ver=1 | T=0   | T=0   | TKL=0 | TKL=0 | TKL=0 | TKL=1 |

Version=1, Type=CON (00), Token length=1. The whole header is 4 bytes — compare that to MQTT's minimum of 2 bytes plus variable-length topic. CoAP is slightly larger per-packet because of the Uri-Path options, but it needs no persistent connection.

---

### ACK 2.05 Content Response

| Field | Bytes | Raw Hex | Decoded |
|-------|-------|---------|---------|
| Header byte 0 | 0 | `61` | Ver=1, Type=ACK (10), TKL=1 |
| Code | 1 | `45` | 2.05 = Content |
| Message ID | 2–3 | `AB CD` | 43981 — matches the request ✓ |
| Token | 4 | `EF` | 0xEF — matches the request ✓ |
| Content-Format option | 5–6 | `C1 32` | Option 12, value 50 = application/json |
| Payload marker | 7 | `FF` | Signals start of payload |
| Payload | 8–… | `7B 22 76 61 6C…` | `{"value":70.312,"unit":"C","ts":"2025-..."}` |

Both the Message ID and Token match the original request. The token is how a client can have multiple outstanding requests in flight — the server echoes it back and the client uses it to figure out which request this response is for. That becomes critical with Observe, where a single subscription token identifies every notification over the 60-second window.

Content-Format = 50 is what a CoAP-HTTP proxy would use to set `Content-Type: application/json` on the HTTP side. That's the core of the Task 2.3 mapping.

---

### Observe Notification

| Field | Value |
|-------|-------|
| Observe option (Option 6) | Sequence number, e.g. 3 |
| Message type | NON — server doesn't require ACK for periodic notifications |
| Response code | 2.05 Content |
| Interval | Every 5 seconds (from `_update_loop`) |

The sequence number increments each time. My observer checks freshness using `(new_seq - last_seq) mod 2²⁴ < 2²³`. Over loopback, notifications always arrive in order so this never fires — but on a real UDP network you can get reordering, and without this check a stale notification could overwrite a fresh reading. In the 60-second run I observed 12 notifications per sensor with 0 stale.

The fact that Observe uses NON by default is interesting — the server sends updates without waiting for acknowledgements. If the client misses one, it just gets the next one 5 seconds later. For continuous sensor telemetry that's fine. If the application needed every update, you'd configure the server to use CON notifications, but then you'd pay an ACK round-trip for every reading.

---

*Module 2 Assignment — Real-Time Data Analytics for IoT*
