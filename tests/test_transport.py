"""Tests for i3x._transport."""

import httpx
import pytest
import respx

from i3x._transport import Transport
from i3x.errors import (
    AuthenticationError,
    ConnectionError,
    I3XError,
    NotFoundError,
    ServerError,
    TimeoutError,
)


@pytest.fixture()
def mock_api():
    with respx.mock(base_url="http://test-server:8080") as router:
        router.get("/namespaces").respond(json=[])
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
    def test_get(self, mock_api, transport):
        mock_api.get("/test").respond(json={"ok": True})
        result = transport.get("/test")
        assert result == {"ok": True}

    def test_get_with_params(self, mock_api, transport):
        mock_api.get("/test").respond(json=[1, 2, 3])
        result = transport.get("/test", params={"key": "value"})
        assert result == [1, 2, 3]

    def test_post(self, mock_api, transport):
        mock_api.post("/test").respond(json={"created": True})
        result = transport.post("/test", json={"data": "value"})
        assert result == {"created": True}

    def test_put(self, mock_api, transport):
        mock_api.put("/test").respond(json={"updated": True})
        result = transport.put("/test", json={"data": "value"})
        assert result == {"updated": True}

    def test_delete(self, mock_api, transport):
        mock_api.delete("/test").respond(json={"deleted": True})
        result = transport.delete("/test")
        assert result == {"deleted": True}


class TestTransportErrorMapping:
    def test_401_raises_auth_error(self, mock_api, transport):
        mock_api.get("/secret").respond(status_code=401, json={"detail": "Unauthorized"})
        with pytest.raises(AuthenticationError):
            transport.get("/secret")

    def test_403_raises_auth_error(self, mock_api, transport):
        mock_api.get("/forbidden").respond(status_code=403, json={"detail": "Forbidden"})
        with pytest.raises(AuthenticationError):
            transport.get("/forbidden")

    def test_404_raises_not_found(self, mock_api, transport):
        mock_api.get("/missing").respond(status_code=404, json={"detail": "Not Found"})
        with pytest.raises(NotFoundError):
            transport.get("/missing")

    def test_500_raises_server_error(self, mock_api, transport):
        mock_api.get("/error").respond(status_code=500, json={"detail": "Internal Error"})
        with pytest.raises(ServerError):
            transport.get("/error")

    def test_unknown_4xx_raises_base_error(self, mock_api, transport):
        mock_api.get("/weird").respond(status_code=422, json={"detail": "Unprocessable"})
        with pytest.raises(I3XError):
            transport.get("/weird")

    def test_error_preserves_status_code(self, mock_api, transport):
        mock_api.get("/missing").respond(status_code=404, json={"detail": "Not Found"})
        with pytest.raises(NotFoundError) as exc_info:
            transport.get("/missing")
        assert exc_info.value.status_code == 404


class TestTransportAuth:
    def test_auth_headers_sent(self, mock_api):
        route = mock_api.get("/namespaces").respond(json=[])
        t = Transport("http://test-server:8080", auth=("my-key", "my-secret"))
        t.open()
        request = route.calls.last.request
        assert request.headers["x-api-key"] == "my-key"
        assert request.headers["x-api-secret"] == "my-secret"
        t.close()
