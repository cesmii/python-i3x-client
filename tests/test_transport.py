"""Tests for i3x._transport."""

import ssl

import httpx
import pytest
import respx

from i3x._transport import Transport, _is_ssl_error
from i3x.errors import (
    AuthenticationError,
    ConnectionError,
    I3XError,
    NotFoundError,
    NotSupportedError,
    ServerError,
    TimeoutError,
)


def error_envelope(title, status, detail):
    return {"success": False, "responseDetail": {"title": title, "status": status, "detail": detail}}


@pytest.fixture()
def mock_api():
    with respx.mock(base_url="http://test-server:8080") as router:
        router.get("/info").respond(json={"success": True, "result": {
            "specVersion": "1.0",
            "capabilities": {"query": {"history": False}, "update": {"current": False, "history": False}, "subscribe": {"stream": True}},
        }})
        yield router


@pytest.fixture()
def transport(mock_api):
    t = Transport("http://test-server:8080")
    t.open()
    yield t
    t.close()


class TestTransportLifecycle:
    def test_open_close(self, mock_api):
        t = Transport("http://test-server:8080")
        assert not t.is_open
        t.open()
        assert t.is_open
        t.close()
        assert not t.is_open

    def test_open_idempotent(self, mock_api):
        t = Transport("http://test-server:8080")
        t.open()
        t.open()  # Should not raise
        assert t.is_open
        t.close()

    def test_get_before_open_raises(self):
        t = Transport("http://test-server:8080")
        with pytest.raises(ConnectionError, match="not connected"):
            t.get("/namespaces")

    def test_strips_trailing_slash(self):
        t = Transport("http://test-server:8080/")
        assert t.base_url == "http://test-server:8080"


class TestTransportRequests:
    def test_get_unwraps_result(self, mock_api, transport):
        mock_api.get("/test").respond(json={"success": True, "result": {"ok": True}})
        result = transport.get("/test")
        assert result == {"ok": True}

    def test_get_unwraps_results_list(self, mock_api, transport):
        mock_api.get("/test").respond(json={"success": True, "results": [1, 2, 3]})
        result = transport.get("/test")
        assert result == [1, 2, 3]

    def test_get_with_params(self, mock_api, transport):
        mock_api.get("/test").respond(json={"success": True, "result": [1, 2, 3]})
        result = transport.get("/test", params={"key": "value"})
        assert result == [1, 2, 3]

    def test_post(self, mock_api, transport):
        mock_api.post("/test").respond(json={"success": True, "result": {"created": True}})
        result = transport.post("/test", json={"data": "value"})
        assert result == {"created": True}

    def test_put(self, mock_api, transport):
        mock_api.put("/test").respond(json={"success": True, "result": None})
        result = transport.put("/test", json={"data": "value"})
        assert result is None

    def test_non_envelope_response_returned_as_is(self, mock_api, transport):
        mock_api.get("/test").respond(json={"some": "data"})
        result = transport.get("/test")
        assert result == {"some": "data"}


class TestTransportErrorMapping:
    def test_401_raises_auth_error(self, mock_api, transport):
        mock_api.get("/secret").respond(status_code=401, json=error_envelope("Unauthorized", 401, "Missing credentials"))
        with pytest.raises(AuthenticationError):
            transport.get("/secret")

    def test_403_raises_auth_error(self, mock_api, transport):
        mock_api.get("/forbidden").respond(status_code=403, json=error_envelope("Forbidden", 403, "Not authorized"))
        with pytest.raises(AuthenticationError):
            transport.get("/forbidden")

    def test_404_raises_not_found(self, mock_api, transport):
        mock_api.get("/missing").respond(status_code=404, json=error_envelope("Not Found", 404, "No such element"))
        with pytest.raises(NotFoundError):
            transport.get("/missing")

    def test_500_raises_server_error(self, mock_api, transport):
        mock_api.get("/error").respond(status_code=500, json=error_envelope("Internal Error", 500, "Boom"))
        with pytest.raises(ServerError):
            transport.get("/error")

    def test_501_raises_not_supported(self, mock_api, transport):
        mock_api.put("/objects/history").respond(status_code=501, json=error_envelope(
            "Not Implemented", 501, "History updates not supported"))
        with pytest.raises(NotSupportedError, match="History updates not supported"):
            transport.put("/objects/history", json={"updates": []})

    def test_unknown_4xx_raises_base_error(self, mock_api, transport):
        mock_api.get("/weird").respond(status_code=422, json=error_envelope("Unprocessable", 422, "Bad input"))
        with pytest.raises(I3XError):
            transport.get("/weird")

    def test_error_preserves_status_code(self, mock_api, transport):
        mock_api.get("/missing").respond(status_code=404, json=error_envelope("Not Found", 404, "No such element"))
        with pytest.raises(NotFoundError) as exc_info:
            transport.get("/missing")
        assert exc_info.value.status_code == 404

    def test_error_message_extracted_from_response_detail(self, mock_api, transport):
        mock_api.get("/missing").respond(status_code=404, json=error_envelope(
            "Not Found", 404, "Element not found: xyz"))
        with pytest.raises(NotFoundError, match="Element not found: xyz"):
            transport.get("/missing")

    def test_error_message_extracted_from_legacy_envelope(self, mock_api, transport):
        # Pre-release servers used {"error": {"code": N, "message": "..."}}
        mock_api.get("/missing").respond(status_code=404, json={
            "success": False, "error": {"code": 404, "message": "Element not found: xyz"}
        })
        with pytest.raises(NotFoundError, match="Element not found: xyz"):
            transport.get("/missing")


class TestTransportRedirects:
    def test_follows_redirect(self):
        with respx.mock(base_url="http://test-server:8080") as router:
            router.get("/info").respond(
                status_code=301, headers={"location": "http://test-server:8080/v1/info"})
            router.get("/v1/info").respond(json={"success": True, "result": {
                "specVersion": "1.0", "capabilities": {}}})
            t = Transport("http://test-server:8080")
            result = t.open()
            assert result.data["specVersion"] == "1.0"
            t.close()

    def test_http_to_https_redirect_rebuilds_client(self):
        # When http:// redirects to https://, the client must be rebuilt so that
        # subsequent POSTs go directly to HTTPS (not re-redirected, which would
        # cause httpx to convert POST → GET, resulting in 405).
        with respx.mock() as router:
            router.get("http://test-server:8080/v1/info").respond(
                status_code=301, headers={"location": "https://test-server:8443/v1/info"})
            router.get("https://test-server:8443/v1/info").respond(json={"success": True, "result": {
                "specVersion": "1.0", "capabilities": {}}})
            t = Transport("http://test-server:8080/v1")
            t.open()
            assert t.base_url == "https://test-server:8443/v1"
            t.close()


class TestTransportTLS:
    def test_is_ssl_error_detects_wrapped_cause(self):
        outer = httpx.ConnectError("certificate verify failed")
        outer.__cause__ = ssl.SSLCertVerificationError("self-signed certificate")
        assert _is_ssl_error(outer) is True

    def test_is_ssl_error_false_for_plain_connect_error(self):
        assert _is_ssl_error(httpx.ConnectError("connection refused")) is False

    def test_ssl_error_maps_to_connection_error_with_guidance(self):
        exc = httpx.ConnectError("certificate verify failed")
        exc.__cause__ = ssl.SSLCertVerificationError("self-signed certificate")
        mapped = Transport._connect_error(exc)
        assert isinstance(mapped, ConnectionError)
        assert "verify=False" in str(mapped)

    def test_plain_connect_error_has_no_tls_guidance(self):
        mapped = Transport._connect_error(httpx.ConnectError("connection refused"))
        assert isinstance(mapped, ConnectionError)
        assert "verify=False" not in str(mapped)
        assert "connection refused" in str(mapped)

    def test_verify_passed_through(self):
        t = Transport("https://test-server", verify=False)
        assert t._verify is False


class TestTransportErrorSafetyNet:
    """No request failure may escape open()/requests as a raw (non-i3X) traceback."""

    def test_invalid_url_maps_to_i3x_error(self):
        # httpx.InvalidURL is NOT a subclass of httpx.HTTPError.
        t = Transport("http://\x01/v1")
        with pytest.raises(I3XError):
            t.open()
        assert not t.is_open

    def test_request_error_passes_through_existing_i3x_error(self):
        t = Transport("http://test-server:8080")
        original = NotFoundError("not found", status_code=404)
        assert t._request_error(original) is original

    def test_request_error_wraps_unexpected_exception(self):
        t = Transport("http://test-server:8080")
        mapped = t._request_error(OSError("disk on fire"))
        assert isinstance(mapped, I3XError)
        assert "disk on fire" in str(mapped)

    def test_request_error_maps_invalid_url(self):
        t = Transport("http://test-server:8080")
        mapped = t._request_error(httpx.InvalidURL("bad url"))
        assert isinstance(mapped, ConnectionError)

    def test_malformed_json_body_maps_to_i3x_error(self):
        with respx.mock(base_url="http://test-server:8080") as router:
            router.get("/info").respond(json={"success": True, "result": {
                "specVersion": "1.0", "capabilities": {}}})
            router.get("/data").respond(
                status_code=200, text="not json",
                headers={"content-type": "application/json"})
            t = Transport("http://test-server:8080")
            t.open()
            with pytest.raises(I3XError, match="malformed JSON"):
                t.get("/data")
            t.close()


class TestTransportAuth:
    def test_basic_auth_tuple_sent(self, mock_api):
        route = mock_api.get("/info").respond(json={"success": True, "result": {
            "specVersion": "1.0",
            "capabilities": {"query": {"history": False}, "update": {"current": False, "history": False}, "subscribe": {"stream": True}},
        }})
        t = Transport("http://test-server:8080", auth=("user", "secret"))
        t.open()
        request = route.calls.last.request
        assert request.headers["authorization"].startswith("Basic ")
        t.close()

    def test_custom_headers_sent(self, mock_api):
        route = mock_api.get("/info").respond(json={"success": True, "result": {
            "specVersion": "1.0",
            "capabilities": {"query": {"history": False}, "update": {"current": False, "history": False}, "subscribe": {"stream": True}},
        }})
        t = Transport("http://test-server:8080", headers={"X-API-Key": "my-key"})
        t.open()
        request = route.calls.last.request
        assert request.headers["x-api-key"] == "my-key"
        t.close()
