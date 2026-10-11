"""Scenario configuration validation for the Tessera core.

The effective configuration is always plain data. Unknown operational fields
are rejected with a field-path diagnostic instead of being silently ignored.
"""

from __future__ import annotations

import json
from typing import Any

MAX_SATELLITES = 10_000
MAX_NAME_LENGTH = 128
MAX_CONFIG_BYTES = 1_048_576  # 1 MiB bound on config payloads


class ConfigError(Exception):
    """Raised when a configuration payload fails validation."""

    def __init__(self, errors: list[dict[str, str]]):
        self.errors = errors
        super().__init__("invalid configuration: " + "; ".join(
            f"{e['path']}: {e['message']}" for e in errors
        ))


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def validate_config(raw: Any) -> dict[str, Any]:
    """Validate a raw configuration payload and return the effective config.

    Raises ConfigError with structured, field-path-identified errors.
    """
    errors: list[dict[str, str]] = []

    if not isinstance(raw, dict):
        raise ConfigError([{"path": "$", "message": "configuration must be a JSON object"}])

    effective: dict[str, Any] = {}

    name = raw.get("name", "unnamed-scenario")
    if not isinstance(name, str):
        errors.append({"path": "$.name", "message": "must be a string"})
    elif len(name) > MAX_NAME_LENGTH:
        errors.append({"path": "$.name", "message": f"must be at most {MAX_NAME_LENGTH} characters"})
    else:
        effective["name"] = name

    satellites = raw.get("satellites", 4)
    if not _is_int(satellites):
        errors.append({"path": "$.satellites", "message": "must be an integer"})
    elif not 1 <= satellites <= MAX_SATELLITES:
        errors.append({"path": "$.satellites", "message": f"must be between 1 and {MAX_SATELLITES}"})
    else:
        effective["satellites"] = satellites

    seed = raw.get("seed", 0)
    if not _is_int(seed):
        errors.append({"path": "$.seed", "message": "must be an integer"})
    else:
        effective["seed"] = seed

    for key in raw:
        if key not in ("name", "satellites", "seed"):
            errors.append({
                "path": f"$.{key}",
                "message": "unknown operational field",
            })

    if errors:
        raise ConfigError(errors)
    return effective


def validate_config_bytes(data: bytes) -> dict[str, Any]:
    """Validate a raw bytes payload, enforcing the size bound."""
    if len(data) > MAX_CONFIG_BYTES:
        raise ConfigError([{
            "path": "$",
            "message": f"configuration exceeds {MAX_CONFIG_BYTES} bytes",
        }])
    try:
        raw = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ConfigError([{"path": "$", "message": f"invalid JSON: {exc}"}]) from exc
    return validate_config(raw)
