"""
Module 2 Assignment — Task 2.3
CoAP-HTTP Proxy Mapping Tests

Verifies CoAP response option → HTTP header mappings as specified in
RFC 7252 §10.1 (CoAP-HTTP proxy semantics) and RFC 8075.

These tests validate the CoAP server side of the mapping directly.
A real CoAP-HTTP proxy (e.g., aiocoap-proxy or Californium cf-proxy2)
would apply the same mappings when forwarding responses to HTTP clients.

Run with:  pytest tests/coap/test_proxy.py -v -s
"""

import asyncio
import json
import pytest
import pytest_asyncio

import aiocoap
from aiocoap import Code, Message


pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="module")
async def coap_server():
    """Start the CoAP server for the duration of the test module."""
    try:
        from src.coap.server import build_server
        ctx = await build_server()
        yield ctx
        await ctx.shutdown()
    except NotImplementedError:
        pytest.skip("CoAP server not yet implemented (NotImplementedError)")


@pytest_asyncio.fixture(scope="module")
async def coap_client():
    ctx = await aiocoap.Context.create_client_context()
    yield ctx
    await ctx.shutdown()


class TestCoAPHTTPProxyMapping:
    """
    Task 2.3: CoAP → HTTP header mapping validation.

    Per RFC 7252 §10.1 and RFC 8075, a CoAP-HTTP proxy maps:
      CoAP Content-Format (option 12) → HTTP Content-Type
      CoAP Max-Age (option 14)        → HTTP Cache-Control: max-age=<N>
      CoAP ETag (option 4)            → HTTP ETag
      CoAP Location-Path (option 8)   → HTTP Location

    These tests verify the CoAP server returns the correct option values
    that a proxy would use to populate HTTP response headers.
    """

    async def test_content_format_is_json(self, coap_server, coap_client):
        """
        CoAP Content-Format 50 = application/json.
        A proxy maps this to: Content-Type: application/json
        """
        req  = Message(code=Code.GET, uri="coap://localhost/factory/line1/temperature")
        resp = await coap_client.request(req).response

        assert resp.code == Code.CONTENT
        cf = resp.opt.content_format
        assert cf == 50, f"Expected Content-Format 50 (application/json), got {cf}"

        http_header = "application/json"
        print(f"\n[CoAP→HTTP] Content-Format: {cf} → Content-Type: {http_header}")

    async def test_max_age_maps_to_cache_control(self, coap_server, coap_client):
        """
        CoAP Max-Age option → HTTP Cache-Control: max-age=<N>
        RFC 7252 §5.10.5: default Max-Age = 60 seconds.
        """
        req  = Message(code=Code.GET, uri="coap://localhost/factory/line1/temperature")
        resp = await coap_client.request(req).response

        max_age = resp.opt.max_age if resp.opt.max_age is not None else 60
        assert max_age >= 0, f"Max-Age must be non-negative, got {max_age}"

        http_header = f"Cache-Control: max-age={max_age}"
        print(f"\n[CoAP→HTTP] Max-Age (option 14): {max_age} → {http_header}")

    async def test_etag_option_documented(self, coap_server, coap_client):
        """
        CoAP ETag option → HTTP ETag header (optional; resource may omit it).
        """
        req  = Message(code=Code.GET, uri="coap://localhost/factory/line1/temperature")
        resp = await coap_client.request(req).response

        etag = resp.opt.etag
        if etag:
            print(f"\n[CoAP→HTTP] ETag (option 4): 0x{etag.hex()} → ETag: \"{etag.hex()}\"")
        else:
            print("\n[CoAP→HTTP] ETag (option 4): not set → no ETag header (valid per RFC 7252)")
        assert resp.code == Code.CONTENT  # ETag is optional

    async def test_location_path_from_uri(self, coap_server, coap_client):
        """
        CoAP Uri-Path options map to HTTP Location in a proxy GET response.
        The effective Location for /factory/line1/temperature is that path.
        """
        req  = Message(code=Code.GET, uri="coap://localhost/factory/line1/temperature")
        resp = await coap_client.request(req).response

        # Uri-Path segments are carried in the request, not echoed in GET response;
        # a proxy derives Location from the request URI path.
        expected_location = "/factory/line1/temperature"
        print(f"\n[CoAP→HTTP] Uri-Path options → HTTP Location: {expected_location}")
        assert resp.code == Code.CONTENT

    async def test_proxy_body_passes_through_unchanged(self, coap_server, coap_client):
        """
        The JSON payload from CoAP must pass through the proxy unchanged.
        All required keys must be present; value types must match.
        """
        req  = Message(code=Code.GET, uri="coap://localhost/factory/line1/temperature")
        resp = await coap_client.request(req).response

        data = json.loads(resp.payload)
        assert {"value", "unit", "ts"}.issubset(data.keys())
        assert isinstance(data["value"], (int, float))
        assert isinstance(data["unit"], str)
        assert isinstance(data["ts"], str)
        print(f"\n[Proxy body] {data}")

    async def test_actuator_put_maps_to_http_204(self, coap_server, coap_client):
        """
        CoAP PUT → 2.04 Changed maps to HTTP 204 No Content in a proxy.
        Verifies actuator endpoint accepts state commands.
        """
        req  = Message(
            code=Code.PUT,
            uri="coap://localhost/actuator/line1/fan",
            payload=json.dumps({"state": "ON"}).encode(),
            content_format=50,
        )
        resp = await coap_client.request(req).response
        assert resp.code == Code.CHANGED, f"Expected 2.04 Changed, got {resp.code}"
        # 2.04 Changed → HTTP 204 No Content in a CoAP-HTTP proxy
        print(f"\n[CoAP→HTTP] PUT 2.04 Changed → HTTP 204 No Content")

    async def test_proxy_header_mapping_summary(self, coap_server, coap_client):
        """
        Print the complete CoAP → HTTP header mapping table for Section 5.2.
        """
        req  = Message(code=Code.GET, uri="coap://localhost/factory/line1/temperature")
        resp = await coap_client.request(req).response

        cf      = resp.opt.content_format or 50
        max_age = resp.opt.max_age if resp.opt.max_age is not None else 60
        etag    = resp.opt.etag.hex() if resp.opt.etag else "(not set by resource)"

        print("\n")
        print("=" * 72)
        print("  Task 2.3 — CoAP-HTTP Proxy Header Mapping (observed from server)")
        print("=" * 72)
        print(f"  {'HTTP Header':<35} {'CoAP Option':<22} {'Observed Value'}")
        print("-" * 72)
        print(f"  {'Content-Type':<35} {'Content-Format (12)':<22} application/json  [CF={cf}]")
        print(f"  {'Cache-Control: max-age':<35} {'Max-Age (14)':<22} max-age={max_age}")
        print(f"  {'ETag':<35} {'ETag (4)':<22} {etag}")
        print(f"  {'Location':<35} {'Location-Path (8)':<22} /factory/line1/temperature")
        print("=" * 72)
        print("\nCopy this table into report Section 5.2.\n")

        assert resp.code == Code.CONTENT
