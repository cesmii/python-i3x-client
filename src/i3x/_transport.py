"""Internal HTTP transport layer wrapping httpx."""

from __future__ import annotations

from typing import Any

import httpx

from . import errors


_STATUS_MAP: dict[int, type[errors.I3XError]] = {
    401: errors.AuthenticationError,
    403: errors.AuthenticationError,
    404: errors.NotFoundError,
}


class Transport:
    """Wraps httpx.Client with error mapping and base URL handling."""

    def __init__(
        self,
        base_url: str,
        auth: tuple[str, str] | None = None,
        timeout: float = 30.0,
    ):
        self._base_url = base_url.rstrip("/")
        self._auth = auth
        self._timeout = timeout
        self._client: httpx.Client | None = None

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def is_open(self) -> bool:
        return self._client is not None

    def open(self) -> None:
        """Open the underlying HTTP client and verify connectivity."""
        if self._client is not None:
            return
        headers = {}
        if self._auth:
            headers["X-API-Key"] = self._auth[0]
            if len(self._auth) > 1:
                headers["X-API-Secret"] = self._auth[1]
        self._client = httpx.Client(
            base_url=self._base_url,
            headers=headers,
            timeout=self._timeout,
        )
        # Verify connectivity with a lightweight request
        try:
            self.get("/namespaces")
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

    def delete(self, path: str) -> Any:
        client = self._ensure_open()
        return self._request(client, "DELETE", path)

    def stream_get(self, path: str) -> httpx.Response:
        """Return a streaming response for SSE endpoints.

        Caller is responsible for closing the response.
        """
        client = self._ensure_open()
        try:
            response = client.send(
                client.build_request("GET", path),
                stream=True,
            )
            self._check_status(response)
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
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            return response.json()
        return response.text

    @staticmethod
    def _check_status(response: httpx.Response) -> None:
        if response.status_code < 400:
            return
        error_cls = _STATUS_MAP.get(response.status_code)
        if error_cls is None:
            if response.status_code >= 500:
                error_cls = errors.ServerError
            else:
                error_cls = errors.I3XError
        try:
            detail = response.json()
            message = detail.get("detail", detail.get("message", response.text))
        except Exception:
            message = response.text
        raise error_cls(str(message), status_code=response.status_code)
