"""Internal HTTP transport layer wrapping httpx."""

from __future__ import annotations

import logging
import ssl
from typing import Any, NamedTuple
from urllib.parse import urlparse, urlunparse

import httpx

from . import errors

logger = logging.getLogger("i3x.transport")


class InfoResult(NamedTuple):
    """The outcome of fetching ``/info`` during connect.

    ``data`` is the unwrapped JSON payload (a dict for a valid i3X server), or
    ``None`` when the response was not parseable JSON. ``status_code`` and
    ``content_type`` are retained so the caller can build a precise error.
    ``final_url`` is the URL of the response after any redirects.
    """

    status_code: int
    content_type: str
    data: Any
    final_url: str = ""


def _is_ssl_error(exc: BaseException) -> bool:
    """True if ``exc`` (or anything it wraps) is a TLS/certificate error."""
    seen: set[int] = set()
    cur: BaseException | None = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        if isinstance(cur, ssl.SSLError):
            return True
        cur = cur.__cause__ or cur.__context__
    return False


class Transport:
    """Wraps httpx.Client with error mapping and base URL handling."""

    def __init__(
        self,
        base_url: str,
        auth: Any = None,
        timeout: float = 30.0,
        headers: dict[str, str] | None = None,
        verify: Any = True,
    ):
        self._base_url = base_url.rstrip("/")
        self._auth = auth
        self._timeout = timeout
        self._headers = dict(headers or {})
        self._verify = verify
        self._client: httpx.Client | None = None

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def is_open(self) -> bool:
        return self._client is not None

    def open(self) -> InfoResult:
        """Open the underlying HTTP client and verify connectivity via GET /info.

        Returns an :class:`InfoResult` carrying the response status, content type,
        and parsed payload so the caller can distinguish a valid i3X server from
        an unrelated endpoint. Transport-level failures (connection, TLS, timeout)
        and HTTP error statuses (401/403/404/5xx) raise as usual.
        """
        try:
            if self._client is None:
                # Constructing the client validates base_url (may raise InvalidURL).
                self._client = httpx.Client(
                    base_url=self._base_url,
                    auth=self._auth,
                    headers=self._headers,
                    timeout=self._timeout,
                    verify=self._verify,
                    follow_redirects=True,
                )
            result = self._fetch_info()
            self._maybe_upgrade_scheme(result.final_url)
            return result
        except Exception as exc:
            self.close()
            raise self._request_error(exc) from exc

    def _fetch_info(self) -> InfoResult:
        """GET /info and return its status, content type, and parsed payload.

        Maps connection/TLS/timeout failures and HTTP error statuses to i3X
        errors. A 2xx response with an empty, non-JSON, or unparseable body
        yields ``data=None`` rather than raising, leaving the caller to decide.
        """
        client = self._ensure_open()
        try:
            response = client.request("GET", "/info")
        except Exception as exc:
            raise self._request_error(exc) from exc

        self._check_status(response)
        content_type = response.headers.get("content-type", "")

        data: Any = None
        if response.content and "application/json" in content_type:
            try:
                data = self._unwrap_envelope(response.json())
            except ValueError:
                data = None
        return InfoResult(response.status_code, content_type, data, str(response.url))

    def _maybe_upgrade_scheme(self, final_info_url: str) -> None:
        """Rebuild the httpx client if ``/info`` redirected to a different scheme.

        When a plain-HTTP base URL redirects to HTTPS, httpx safely follows the
        redirect for GET /info (because GETs are idempotent). But subsequent POST
        and PUT requests would be redirected too, and HTTP 301/302 redirect
        semantics convert POST to GET — causing 405 Method Not Allowed on the
        HTTPS endpoint. Detecting the scheme change here and rebuilding the client
        with the HTTPS base URL avoids the problem entirely.
        """
        if not final_info_url or self._client is None:
            return
        orig = urlparse(self._base_url)
        final = urlparse(final_info_url)
        if orig.scheme == final.scheme:
            return
        # Strip the trailing /info that httpx appended to form the request URL.
        path = final.path
        if not path.endswith("/info"):
            return  # unexpected URL shape — don't guess
        new_base = urlunparse((final.scheme, final.netloc, path[:-5], "", "", ""))
        logger.debug("Scheme redirect %s → %s: rebuilding client", self._base_url, new_base)
        self._base_url = new_base
        old = self._client
        self._client = httpx.Client(
            base_url=new_base,
            auth=self._auth,
            headers=self._headers,
            timeout=self._timeout,
            verify=self._verify,
            follow_redirects=True,
        )
        old.close()

    def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._client is not None:
            self._client.close()
            self._client = None

    def _ensure_open(self) -> httpx.Client:
        if self._client is None:
            raise errors.ConnectionError("Transport is not connected. Call open() first.")
        return self._client

    @staticmethod
    def _connect_error(exc: BaseException) -> errors.ConnectionError:
        """Map a connect/transport failure to a ConnectionError, with TLS guidance."""
        if _is_ssl_error(exc):
            return errors.ConnectionError(
                f"TLS certificate verification failed: {exc}. If you are connecting "
                "to a development or test server with a self-signed certificate, pass "
                "verify=False (to skip verification) or verify='/path/to/ca.pem' (to "
                "trust a custom CA) when constructing the client, e.g. "
                "i3x.Client(url, verify=False)."
            )
        return errors.ConnectionError(str(exc))

    def _request_error(self, exc: BaseException) -> errors.I3XError:
        """Map any exception raised while issuing a request to an I3XError.

        Guarantees a request failure never escapes as a raw traceback: known
        httpx errors map to their specific i3X type; anything else (e.g.
        ``httpx.InvalidURL``, ``OSError``, or an unexpected error) falls back to
        a ConnectionError rather than propagating unwrapped.
        """
        if isinstance(exc, errors.I3XError):
            return exc  # already mapped (e.g. by _check_status); don't re-wrap
        if isinstance(exc, httpx.ConnectError):
            return self._connect_error(exc)
        if isinstance(exc, httpx.TimeoutException):
            return errors.TimeoutError(str(exc))
        if isinstance(exc, httpx.HTTPError):
            return errors.I3XError(str(exc))
        return self._connect_error(exc)

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
        except Exception as exc:
            raise self._request_error(exc) from exc

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
        except Exception as exc:
            raise self._request_error(exc) from exc

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

        try:
            body = response.json()
        except ValueError as exc:
            raise errors.I3XError(
                f"Server returned malformed JSON for {method} {path}: {exc}"
            ) from exc
        return self._unwrap_envelope(body)

    @staticmethod
    def _unwrap_envelope(body: Any) -> Any:
        """Unwrap the standard i3X response envelope.

        Simple success: ``{"success": true, "result": <data>}``  → ``<data>``.
        Bulk response:  ``{"success": bool, "results": [...]}``   → the list.
        Anything else is returned unchanged.
        """
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
