"""Scenario configuration loading for the ConstellaLab core.

Configuration is validated against ``$defs/SimulationConfig`` of the contract
schema. Unknown fields, bad units/ranges and incompatible schema versions are
rejected with field-path diagnostics instead of being silently ignored.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .contract import ContractError, SimulationConfig

MAX_CONFIG_BYTES = 1_048_576  # 1 MiB bound on config payloads

DATA_DIR = Path(__file__).with_name("data")
BUILTIN_SCENARIOS = {
    "empty": DATA_DIR / "scenario_empty.json",
    "visual-orbit-demo": DATA_DIR / "scenario_four_satellites.json",
}
DEFAULT_SCENARIO = "visual-orbit-demo"


class ConfigError(ContractError):
    """Raised when a configuration payload fails validation."""


def load_config(raw: Any) -> SimulationConfig:
    """Validate a decoded JSON payload and return the typed configuration."""
    try:
        return SimulationConfig.from_dict(raw)
    except ContractError as exc:
        raise ConfigError(exc.errors) from None


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
    target = BUILTIN_SCENARIOS.get(str(path), Path(path))
    try:
        data = target.read_bytes()
    except OSError as exc:
        raise ConfigError([{"path": "$", "message": str(exc)}]) from exc
    return load_config(validate_config_bytes(data))


def builtin_scenario(name: str = DEFAULT_SCENARIO) -> SimulationConfig:
    return load_config_file(name)
