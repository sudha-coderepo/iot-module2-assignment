#!/usr/bin/env bash
# capture.sh — capture MQTT, CoAP, and AMQP traffic for Task 4
# Requires: tshark  (sudo apt install tshark  or  brew install wireshark)

set -e

DURATION=30
IFACE="10"          # loopback — adjust to your interface name
OUTDIR="captures"

mkdir -p "$OUTDIR"

echo "Starting $DURATION-second packet capture on interface $IFACE..."
echo "Make sure your publisher/server/producer is running in another terminal."
echo ""

# Capture all three protocols simultaneously in the background
echo "[1/3] Capturing MQTT (port 1883)..."
"/mnt/c/Program Files/Wireshark/tshark.exe" -i "$IFACE" -f "port 1883" -w "$OUTDIR/mqtt.pcap" -a duration:"$DURATION" &
PID_MQTT=$!

echo "[2/3] Capturing CoAP (port 5683 UDP)..."
"/mnt/c/Program Files/Wireshark/tshark.exe" -i "$IFACE" -f "udp port 5683" -w "$OUTDIR/coap.pcap" -a duration:"$DURATION" &
PID_COAP=$!

echo "[3/3] Capturing AMQP (port 5672)..."
"/mnt/c/Program Files/Wireshark/tshark.exe" -i "$IFACE" -f "port 5672" -w "$OUTDIR/amqp.pcap" -a duration:"$DURATION" &
PID_AMQP=$!

echo ""
echo "Capturing for $DURATION seconds... (Ctrl-C to stop early)"
wait $PID_MQTT $PID_COAP $PID_AMQP

echo ""
echo "Captures saved:"
ls -lh "$OUTDIR/"*.pcap 2>/dev/null || echo "  (no pcap files found — is tshark installed?)"

echo ""
echo "Quick check (first 5 MQTT packets):"
"/mnt/c/Program Files/Wireshark/tshark.exe" -r "$OUTDIR/mqtt.pcap" -Y mqtt 2>/dev/null | head -5 || true
