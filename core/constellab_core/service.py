"""ConstellaLab core service: status, contract schema, config validation and snapshots.

Pure standard library. The service is the single source of truth for version,
clock and orbital state; the renderer only displays the snapshots it is given.
"""

from __future__ import annotations

import json
import platform
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from . import SCHEMA_VERSION, __version__
from .config import MAX_CONFIG_BYTES, ConfigError, builtin_scenario, validate_config_bytes
from .contract import SCHEMA, ContractError, SimulationConfig
from .orbit import initial_snapshot

ROUTES = {
    ("GET", "/api/status"): "status",
    ("GET", "/api/health"): "health",
    ("GET", "/api/contract"): "contract",
    ("GET", "/api/scenario"): "scenario",
    ("GET", "/api/snapshot"): "snapshot",
    ("POST", "/api/config/validate"): "validate",
    ("POST", "/api/snapshot"): "snapshot_for_config",
}

# Local-only bridge: the renderer (Vite dev server or packaged file://) is a
# different origin, so answer CORS preflight for it.
CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
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
    server_version = f"ConstellaLabCore/{__version__}"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("[constellab-core] %s - %s\n" % (self.address_string(), fmt % args))

    @property
    def scenario(self) -> SimulationConfig:
        return self.server.scenario  # type: ignore[attr-defined]

    def _send(self, code: int, payload: Any) -> None:
        body = _json_bytes(payload)
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        for name, value in CORS_HEADERS.items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def _not_found(self) -> None:
        self._send(404, {"error": "not_found", "path": self.path})

    def _route(self, method: str) -> str | None:
        return ROUTES.get((method, self.path.split("?", 1)[0]))

    def _read_body(self) -> bytes | None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._send(400, {"error": "invalid_content_length"})
            return None
        if length > MAX_CONFIG_BYTES:
            self._send(413, {"error": "payload_too_large"})
            return None
        return self.rfile.read(length) if length > 0 else b""

    def do_OPTIONS(self) -> None:  # noqa: N802 (stdlib naming)
        self.send_response(204)
        for name, value in CORS_HEADERS.items():
            self.send_header(name, value)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802 (stdlib naming)
        route = self._route("GET")
        if route == "status":
            self._send(200, status_payload())
        elif route == "health":
            self._send(200, {"status": "ok", "version": __version__})
        elif route == "contract":
            self._send(200, SCHEMA)
        elif route == "scenario":
            self._send(200, self.scenario.to_dict())
        elif route == "snapshot":
            self._send(200, initial_snapshot(self.scenario).to_dict())
        else:
            self._not_found()

    def do_POST(self) -> None:  # noqa: N802 (stdlib naming)
        route = self._route("POST")
        if route not in ("validate", "snapshot_for_config"):
            self._not_found()
            return
        data = self._read_body()
        if data is None:
            return
        try:
            effective = validate_config_bytes(data)
        except ConfigError as exc:
            self._send(422, {"valid": False, "errors": exc.errors})
            return
        if route == "validate":
            self._send(200, {"valid": True, "effective_config": effective})
        else:
            try:
                self._send(200, initial_snapshot(SimulationConfig.from_dict(effective)).to_dict())
            except ContractError as exc:  # pragma: no cover - effective config is already valid
                self._send(500, {"error": "snapshot_failed", "errors": exc.errors})


def serve(host: str = "127.0.0.1", port: int = 0, scenario: SimulationConfig | None = None) -> ThreadingHTTPServer:
    """Start the core HTTP server. port=0 picks a free ephemeral port."""
    server = ThreadingHTTPServer((host, port), CoreHandler)
    server.scenario = scenario or builtin_scenario()  # type: ignore[attr-defined]
    return server
