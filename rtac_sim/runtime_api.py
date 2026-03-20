from __future__ import annotations

import json
import ssl
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import error, request


class RuntimeApiError(RuntimeError):
    """Raised when the OpenPLC runtime API returns an error."""


@dataclass
class ResponsePayload:
    status_code: int
    payload: Any


class OpenPLCRuntimeClient:
    """Minimal stdlib client for the OpenPLC Runtime HTTPS API."""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self._token: str | None = None
        self._ssl_context = ssl._create_unverified_context()

    def is_reachable(self) -> bool:
        try:
            response = self._request_json("/get-users-info", method="GET", auth=False)
        except RuntimeApiError:
            return False
        return response.status_code in (200, 404)

    def ensure_user(self, username: str, password: str, role: str = "admin") -> None:
        users_response = self._request_json("/get-users-info", method="GET", auth=False)
        if users_response.status_code == 404:
            payload = {"username": username, "password": password, "role": role}
            response = self._request_json(
                "/create-user",
                method="POST",
                data=payload,
                auth=False,
            )
            if response.status_code != 201:
                raise RuntimeApiError(f"Unexpected create-user response: {response.payload}")

    def login(self, username: str, password: str) -> str:
        response = self._request_json(
            "/login",
            method="POST",
            data={"username": username, "password": password},
            auth=False,
        )
        if response.status_code != 200 or not isinstance(response.payload, dict):
            raise RuntimeApiError(f"Login failed: {response.payload}")
        token = response.payload.get("access_token")
        if not token:
            raise RuntimeApiError(f"Login did not return a token: {response.payload}")
        self._token = token
        return token

    def status(self) -> dict[str, Any]:
        return self._request_json("/status", method="GET").payload

    def upload_zip(self, zip_path: Path) -> dict[str, Any]:
        zip_bytes = zip_path.read_bytes()
        boundary = f"----CodexBoundary{uuid.uuid4().hex}"
        body_parts = [
            (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="file"; filename="{zip_path.name}"\r\n'
                "Content-Type: application/zip\r\n\r\n"
            ).encode("utf-8"),
            zip_bytes,
            f"\r\n--{boundary}--\r\n".encode("utf-8"),
        ]
        body = b"".join(body_parts)
        headers = {
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Content-Length": str(len(body)),
        }
        return self._request_json(
            "/upload-file",
            method="POST",
            data=body,
            raw=True,
            extra_headers=headers,
        ).payload

    def compilation_status(self) -> dict[str, Any]:
        return self._request_json("/compilation-status", method="GET").payload

    def wait_for_compilation(
        self,
        timeout_seconds: int = 120,
        poll_interval_seconds: float = 1.0,
    ) -> dict[str, Any]:
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            status = self.compilation_status()
            if status["status"] in {"SUCCESS", "FAILED"}:
                return status
            time.sleep(poll_interval_seconds)
        raise RuntimeApiError("Timed out while waiting for compilation to finish")

    def wait_for_runtime_status(
        self,
        expected_fragment: str,
        *,
        timeout_seconds: int = 30,
        poll_interval_seconds: float = 1.0,
    ) -> dict[str, Any]:
        deadline = time.time() + timeout_seconds
        last_status: dict[str, Any] | None = None
        while time.time() < deadline:
            last_status = self.status()
            if expected_fragment in str(last_status.get("status", "")):
                return last_status
            time.sleep(poll_interval_seconds)
        raise RuntimeApiError(
            f"Timed out waiting for runtime status containing {expected_fragment!r}: {last_status}"
        )

    def _request_json(
        self,
        path: str,
        *,
        method: str,
        data: bytes | dict[str, Any] | None = None,
        auth: bool = True,
        raw: bool = False,
        extra_headers: dict[str, str] | None = None,
    ) -> ResponsePayload:
        if auth and not self._token:
            raise RuntimeApiError("Authentication required but no token is set")

        url = f"{self.base_url}{path}"
        headers = {"Accept": "application/json"}
        if auth and self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        if extra_headers:
            headers.update(extra_headers)

        payload = data
        if isinstance(data, dict):
            payload = json.dumps(data).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = request.Request(url, data=payload, headers=headers, method=method)
        try:
            with request.urlopen(req, context=self._ssl_context, timeout=15) as response:
                body = response.read().decode("utf-8")
                parsed = json.loads(body) if body else {}
                return ResponsePayload(response.status, parsed)
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8")
            try:
                parsed = json.loads(body)
            except json.JSONDecodeError:
                parsed = {"raw": body}
            return ResponsePayload(exc.code, parsed)
        except error.URLError as exc:
            raise RuntimeApiError(f"Failed to reach runtime API at {url}: {exc}") from exc
