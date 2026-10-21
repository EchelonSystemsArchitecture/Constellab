"""Scenario configuration loading for the ConstellaLab core.

Configuration is validated against ``$defs/SimulationConfig`` of the contract
schema. Unknown fields, bad units/ranges and incompatible schema versions are
rejected with field-path diagnostics instead of being silently ignored.

Built-in scenarios are either checked-in JSON files or generated Walker-delta
constellations. Generation is deterministic (seeded, no randomness) so a
1,000-satellite scenario needs no 1 MB fixture in the repository while still
being a normal config payload that the same validator accepts.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .contract import ContractError, SimulationConfig
from .dynamics import DEFAULT_MODEL_KEY, registered_models

MAX_CONFIG_BYTES = 1_048_576  # 1 MiB bound on config payloads

DATA_DIR = Path(__file__).with_name("data")

# Large-fleet scenarios: name -> satellite count. Built on demand by
# ``walker_delta_payload`` and validated exactly like a file on disk.
GENERATED_SCENARIOS: dict[str, int] = {
    "swarm-100": 100,
    "swarm-500": 500,
    "swarm-1000": 1000,
}

BUILTIN_SCENARIOS: dict[str, Path | None] = {
    "empty": DATA_DIR / "scenario_empty.json",
    "visual-orbit-demo": DATA_DIR / "scenario_four_satellites.json",
    "swarm-48": DATA_DIR / "scenario_swarm_48.json",
    **{name: None for name in GENERATED_SCENARIOS},
}
DEFAULT_SCENARIO = "visual-orbit-demo"

# Walker-delta geometry for the generated fleets.
FLEET_ALTITUDE_KM = 550.0
FLEET_INCLINATION_DEG = 53.0
FLEET_PLANES = {"swarm-100": 10, "swarm-500": 20, "swarm-1000": 25}
FLEET_TIME_SCALE = 60.0
FLEET_EPOCH_UTC = "2026-10-12T00:00:00Z"


class ConfigError(ContractError):
    """Raised when a configuration payload fails validation."""


def walker_delta_payload(count: int, *, planes: int) -> dict[str, Any]:
    """A deterministic Walker-delta constellation of ``count`` satellites.

    Satellites are spread evenly over ``planes`` orbital planes with an
    inter-plane phase offset, exactly like a real Walker-delta shell: every
    plane shares a semi-major axis, eccentricity and inclination, and only the
    RAAN and the epoch true anomaly differ. That makes the fixture exercise the
    renderer's path de-duplication instead of hiding it behind 1,000 unique
    orbits.
    """
    if count <= 0 or planes <= 0 or count % planes != 0:
        raise ValueError("count must be a positive multiple of planes")
    per_plane = count // planes
    semi_major_axis_km = round(6378.137 + FLEET_ALTITUDE_KM, 6)
    satellites = []
    for index in range(count):
        plane = index % planes
        slot = index // planes
        raan = (plane * 360.0 / planes) % 360.0
        anomaly = (slot * 360.0 / per_plane + plane * 360.0 / count) % 360.0
        satellites.append({
            "id": f"wl-{index:04d}",
            "name": f"WL-{plane + 1:02d}/{slot + 1:03d}",
            "orbit": {
                "semi_major_axis_km": semi_major_axis_km,
                "eccentricity": 0.0,
                "inclination_deg": FLEET_INCLINATION_DEG,
                "raan_deg": round(raan, 6),
                "argument_of_perigee_deg": 0.0,
                "true_anomaly_deg": round(anomaly, 6),
            },
        })
    return {
        "schema_version": _schema_version(),
        "scenario_id": f"swarm-{count}",
        "name": f"Walker-delta {count} ({planes} planes × {per_plane})",
        "seed": count,
        "epoch_utc": FLEET_EPOCH_UTC,
        "time_scale": FLEET_TIME_SCALE,
        "dynamics_model": DEFAULT_MODEL_KEY,
        "satellites": satellites,
    }


def _schema_version() -> str:
    # Imported lazily so ``walker_delta_payload`` stays usable without importing
    # the whole contract model graph twice.
    from . import SCHEMA_VERSION

    return SCHEMA_VERSION


def _validate_dynamics_model(config: SimulationConfig) -> SimulationConfig:
    key = config.dynamics_model or DEFAULT_MODEL_KEY
    if key not in registered_models():
        raise ConfigError([{
            "path": "$.dynamics_model",
            "message": f"unknown dynamics model {key!r}; registered models: "
                       f"{', '.join(sorted(registered_models()))}",
        }])
    return config


def load_config(raw: Any) -> SimulationConfig:
    """Validate a decoded JSON payload and return the typed configuration."""
    try:
        config = SimulationConfig.from_dict(raw)
    except ContractError as exc:
        raise ConfigError(exc.errors) from None
    return _validate_dynamics_model(config)


def validate_config(raw: Any) -> dict[str, Any]:
    """Validate and return the effective configuration as plain data (defaults applied)."""
    return load_config(raw).to_dict()


def validate_config_bytes(data: bytes) -> dict[str, Any]:
    """Validate a raw bytes payload, enforcing the size bound."""
    if len(data) > MAX_CONFIG_BYTES:
        raise ConfigError([{"path": "$", "message": f"configuration exceeds {MAX_CONFIG_BYTES} bytes"}])
    try:
        raw = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ConfigError([{"path": "$", "message": f"invalid JSON: {exc}"}]) from exc
    return validate_config(raw)


def load_config_file(path: str | Path) -> SimulationConfig:
    """Load a scenario file; ``path`` may also name a built-in scenario."""
    name = str(path)
    if name in BUILTIN_SCENARIOS:
        fixture = BUILTIN_SCENARIOS[name]
        if fixture is None:
            return load_config(walker_delta_payload(GENERATED_SCENARIOS[name], planes=FLEET_PLANES[name]))
        target = fixture
    else:
        target = Path(path)
    try:
        data = target.read_bytes()
    except OSError as exc:
        raise ConfigError([{"path": "$", "message": str(exc)}]) from exc
    return load_config(validate_config_bytes(data))


def builtin_scenario(name: str = DEFAULT_SCENARIO) -> SimulationConfig:
    return load_config_file(name)


def scenario_catalog() -> list[dict[str, Any]]:
    """Describe every built-in scenario for the renderer's scenario picker.

    The summary is derived from the validated configuration itself, so it can not
    drift from what ``load_config_file`` will actually start.
    """
    catalog = []
    for name in BUILTIN_SCENARIOS:
        config = builtin_scenario(name)
        catalog.append({
            "key": name,
            "scenario_id": config.scenario_id,
            "name": config.label,
            "satellites": len(config.satellites),
            "epoch_utc": config.epoch_utc,
            "time_scale": config.time_scale,
            "dynamics_model": config.dynamics_model or DEFAULT_MODEL_KEY,
            "generated": name in GENERATED_SCENARIOS,
        })
    return catalog
