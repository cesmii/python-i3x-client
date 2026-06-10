"""Internal HTTP transport layer wrapping httpx."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from . import errors

logger = logging.getLogger("i3x.transport")


class Transport:
    """Wraps httpx.Client with error mapping and base URL handling."""

    def __init__(
        self,
        base_url: str,
        auth: Any = None,
        timeout: float = 30.0,
        headers: dict[str, str] | None = None,
    ):
        self._base_url = base_url.rstrip("/")
        self._auth = auth
        self._timeout = timeout
        self._headers = dict(headers or {})
        self._client: httpx.Client | None = None

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def is_open(self) -> bool:
        return self._client is not None

    def open(self) -> Any:
        """Open the underlying HTTP client and verify connectivity via GET /info.

        Returns the parsed /info payload so callers can inspect the server's
        specVersion without an extra round trip.
        """
        if self._client is not None:
            return self.get("/info")
        self._client = httpx.Client(
            base_url=self._base_url,
            auth=self._auth,
            headers=self._headers,
            timeout=self._timeout,
        )
        try:
            return self.get("/info")
        except Exception:
            self.close()
            raise

    def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._client is not None:
            self._client.close()
            self._client = None

    def _ensure_open(self) -> httpx.Client:
        if self._client is None:
            raise errors.ConnectionError("Transport is not connected. Call open() first.")
        return self._client

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        client = self._ensure_open()
        return self._request(client, "GET", path, params=params)

    def post(self, path: str, json: Any = None) -> Any:
        client = self._ensure_open()
        return self._request(client, "POST", path, json=json)

    def put(self, path: str, json: Any = None) -> Any:
        client = self._ensure_open()
        return self._request(client, "PUT", path, json=json)

    def stream_post(self, path: str, json: Any = None) -> httpx.Response:
        """Return a streaming response for SSE endpoints (POST-based).

        The read timeout is disabled because an SSE stream may legitimately
        stay silent for longer than the request timeout between events.
        Caller is responsible for closing the response.
        """
        client = self._ensure_open()
        try:
            response = client.send(
                client.build_request(
                    "POST",
                    path,
                    json=json,
                    timeout=httpx.Timeout(self._timeout, read=None),
                ),
                stream=True,
            )
            if response.status_code >= 400:
                # Drain the body so _check_status can parse the error envelope.
                try:
                    response.read()
                    self._check_status(response)
                finally:
                    response.close()
            return response
        except httpx.ConnectError as exc:
            raise errors.ConnectionError(str(exc)) from exc
        except httpx.TimeoutException as exc:
            raise errors.TimeoutError(str(exc)) from exc

    def _request(
        self,
        client: httpx.Client,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json: Any = None,
    ) -> Any:
        try:
            response = client.request(method, path, params=params, json=json)
        except httpx.ConnectError as exc:
            raise errors.ConnectionError(str(exc)) from exc
        except httpx.TimeoutException as exc:
            raise errors.TimeoutError(str(exc)) from exc
        except httpx.HTTPError as exc:
            raise errors.I3XError(str(exc)) from exc

        self._check_status(response)

        if response.status_code == 204:
            return None
        if response.status_code == 206:
            logger.warning(
                "Server returned 206 Partial Content for %s %s: "
                "a server-imposed limit was reached and the result is incomplete.",
                method, path,
            )
        content_type = response.headers.get("content-type", "")
        if "application/json" not in content_type:
            return response.text

        body = response.json()

        # Unwrap the standard i3X response envelope.
        # Simple success: {"success": true, "result": <data>}  → return result
        # Bulk response:  {"success": bool, "results": [...]}  → return results list
        if isinstance(body, dict):
            if "result" in body:
                return body["result"]
            if "results" in body:
                return body["results"]

        return body

    @staticmethod
    def _check_status(response: httpx.Response) -> None:
        if response.status_code < 400:
            return
        error_cls = errors.for_status(response.status_code)
        try:
            detail = response.json()
            message = response.text
            if isinstance(detail, dict):
                # i3X 1.0 envelope: {"success": false,
                #   "responseDetail": {"title": "...", "status": N, "detail": "..."}}
                response_detail = detail.get("responseDetail")
                if isinstance(response_detail, dict):
                    message = response_detail.get("detail") or response_detail.get("title") or message
                else:
                    # Pre-release envelopes.
                    error_obj = detail.get("error")
                    if isinstance(error_obj, dict):
                        message = error_obj.get("message", message)
                    else:
                        message = detail.get("detail", detail.get("message", message))
        except Exception:
            message = response.text
        raise error_cls(str(message), status_code=response.status_code)
