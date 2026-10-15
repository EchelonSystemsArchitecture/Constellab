"""ConstellaLab core service: status, contract schema, config validation and snapshots.

Pure standard library. The service is the single source of truth for version,
clock and orbital state; the renderer only displays the snapshots it is given.
"""

from __future__ import annotations

import json
import platform
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from . import SCHEMA_VERSION, __version__
from .config import MAX_CONFIG_BYTES, ConfigError, builtin_scenario, validate_config_bytes
from .contract import SCHEMA, ContractError, SimulationClock, SimulationConfig
from .orbit import initial_snapshot, snapshot_at_time

ROUTES = {
    ("GET", "/api/status"): "status",
    ("GET", "/api/health"): "health",
    ("GET", "/api/contract"): "contract",
    ("GET", "/api/scenario"): "scenario",
    ("GET", "/api/snapshot"): "snapshot",
    ("GET", "/api/clock"): "clock_get",
    ("POST", "/api/clock/pause"): "clock_pause",
    ("POST", "/api/clock/resume"): "clock_resume",
    ("POST", "/api/clock/reset"): "clock_reset",
    ("POST", "/api/clock/step"): "clock_step",
    ("POST", "/api/clock/time_scale"): "clock_time_scale",
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

    @property
    def clock(self) -> SimulationClock:
        return self.server.clock  # type: ignore[attr-defined]

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
            clock = self.clock
            snap = snapshot_at_time(self.scenario, clock.simulation_time_s, clock)
            self._send(200, snap.to_dict())
        elif route == "clock_get":
            self._send(200, self.clock.to_dict())
        else:
            self._not_found()

    def do_POST(self) -> None:  # noqa: N802 (stdlib naming)
        route = self._route("POST")
        if route in ("validate", "snapshot_for_config"):
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
            return

        if route.startswith("clock_"):
            data = self._read_body() or b""
            try:
                payload = json.loads(data) if data else {}
            except json.JSONDecodeError:
                self._send(400, {"error": "invalid_json"})
                return

            with self.server._clock_lock:
                clock = self.server.clock
                if route == "clock_pause":
                    if not clock.paused:
                        clock = SimulationClock(
                            epoch_utc=clock.epoch_utc,
                            simulation_time_s=clock.simulation_time_s,
                            time_scale=clock.time_scale,
                            paused=True,
                        )
                        self.server.clock = clock
                elif route == "clock_resume":
                    if clock.paused:
                        clock = SimulationClock(
                            epoch_utc=clock.epoch_utc,
                            simulation_time_s=clock.simulation_time_s,
                            time_scale=clock.time_scale,
                            paused=False,
                        )
                        self.server.clock = clock
                elif route == "clock_reset":
                    epoch = self.server.scenario.initial_clock()
                    clock = SimulationClock(
                        epoch_utc=epoch.epoch_utc,
                        simulation_time_s=0.0,
                        time_scale=epoch.time_scale,
                        paused=epoch.paused,
                    )
                    self.server.clock = clock
                elif route == "clock_step":
                    # Single step: advance by one simulation second (regardless of time_scale)
                    clock = SimulationClock(
                        epoch_utc=clock.epoch_utc,
                        simulation_time_s=clock.simulation_time_s + 1.0,
                        time_scale=clock.time_scale,
                        paused=clock.paused,
                    )
                    self.server.clock = clock
                elif route == "clock_time_scale":
                    new_scale = payload.get("time_scale")
                    if not isinstance(new_scale, (int, float)) or new_scale <= 0:
                        self._send(400, {"error": "time_scale must be a positive number"})
                        return
                    # Clamp to reasonable bounds
                    new_scale = max(0.001, min(1_000_000, new_scale))
                    clock = SimulationClock(
                        epoch_utc=clock.epoch_utc,
                        simulation_time_s=clock.simulation_time_s,
                        time_scale=new_scale,
                        paused=clock.paused,
                    )
                    self.server.clock = clock
                else:
                    self._not_found()
                    return
            self._send(200, self.server.clock.to_dict())
            return

        self._not_found()


class CoreServer(ThreadingHTTPServer):
    """ThreadingHTTPServer with a mutable simulation clock and auto-advance."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.scenario = builtin_scenario()
        self.clock = running_clock(self.scenario)
        self._clock_lock = threading.Lock()
        self._advance_thread: threading.Thread | None = None
        self._stop_advance = threading.Event()

    def start_advance(self):
        if self._advance_thread is None or not self._advance_thread.is_alive():
            self._stop_advance.clear()
            self._advance_thread = threading.Thread(target=self._advance_loop, daemon=True)
            self._advance_thread.start()

    def stop_advance(self):
        self._stop_advance.set()
        if self._advance_thread:
            self._advance_thread.join(timeout=1.0)

    def _advance_loop(self):
        last_wall = time.monotonic()
        while not self._stop_advance.is_set():
            time.sleep(0.1)
            now = time.monotonic()
            dt = now - last_wall
            last_wall = now
            with self._clock_lock:
                if not self.clock.paused:
                    self.clock = SimulationClock(
                        epoch_utc=self.clock.epoch_utc,
                        simulation_time_s=self.clock.simulation_time_s + dt * self.clock.time_scale,
                        time_scale=self.clock.time_scale,
                        paused=self.clock.paused,
                    )


def running_clock(scenario: SimulationConfig) -> SimulationClock:
    """A clock that already advances time at the scenario's ``time_scale``.

    ``initial_snapshot`` keeps the epoch clock paused (it is the t = 0 state),
    but the running service starts immediately so the renderer sees motion.
    """
    epoch = scenario.initial_clock()
    return SimulationClock(
        epoch_utc=epoch.epoch_utc,
        simulation_time_s=0.0,
        time_scale=epoch.time_scale,
        paused=False,
    )


def serve(host: str = "127.0.0.1", port: int = 0, scenario: SimulationConfig | None = None) -> CoreServer:
    """Start the core HTTP server. port=0 picks a free ephemeral port."""
    server = CoreServer((host, port), CoreHandler)
    server.scenario = scenario or builtin_scenario()  # type: ignore[attr-defined]
    server.clock = running_clock(server.scenario)
    server.start_advance()
    return server