"""ConstellaLab core service: status payload, health endpoint and config validation.

Pure standard library. The service is the single source of truth for version
and health information; the renderer only displays what it is given.
"""

from __future__ import annotations

import json
import platform
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from . import SCHEMA_VERSION, __version__
from .config import MAX_CONFIG_BYTES, ConfigError, validate_config_bytes

ROUTES = {
    ("GET", "/api/status"): "status",
    ("GET", "/api/health"): "health",
    ("POST", "/api/config/validate"): "validate",
}


def status_payload() -> dict[str, Any]:
    """Build the canonical version/status payload."""
    return {
        "name": "constellab-core",
        "version": __version__,
        "schema_version": SCHEMA_VERSION,
        "status": "ok",
        "python_version": platform.python_version(),
        "platform": sys.platform,
        "utc_time": datetime.now(timezone.utc).isoformat(),
        "endpoints": [f"{method} {path}" for method, path in ROUTES],
    }


def _json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


class CoreHandler(BaseHTTPRequestHandler):
    server_version = "ConstellaLabCore/0.1"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("[constellab-core] %s - %s\n" % (self.address_string(), fmt % args))

    def _send(self, code: int, payload: Any) -> None:
        body = _json_bytes(payload)
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _not_found(self) -> None:
        self._send(404, {"error": "not_found", "path": self.path})

    def do_GET(self) -> None:  # noqa: N802 (stdlib naming)
        route = ROUTES.get(("GET", self.path.split("?", 1)[0]))
        if route == "status":
            self._send(200, status_payload())
        elif route == "health":
            self._send(200, {"status": "ok", "version": __version__})
        else:
            self._not_found()

    def do_POST(self) -> None:  # noqa: N802 (stdlib naming)
        route = ROUTES.get(("POST", self.path.split("?", 1)[0]))
        if route != "validate":
            self._not_found()
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._send(400, {"error": "invalid_content_length"})
            return
        if length > MAX_CONFIG_BYTES:
            self._send(413, {"error": "payload_too_large"})
            return
        data = self.rfile.read(length) if length > 0 else b""
        try:
            effective = validate_config_bytes(data)
        except ConfigError as exc:
            self._send(422, {"valid": False, "errors": exc.errors})
            return
        self._send(200, {"valid": True, "effective_config": effective})


def serve(host: str = "127.0.0.1", port: int = 0) -> ThreadingHTTPServer:
    """Start the core HTTP server. port=0 picks a free ephemeral port."""
    server = ThreadingHTTPServer((host, port), CoreHandler)
    return server
