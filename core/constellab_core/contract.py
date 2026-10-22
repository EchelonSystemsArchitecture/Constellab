"""Typed simulation/visualization contract (Day 2).

The JSON Schema in ``data/simulation_contract.schema.json`` is the single
versioned source. The dataclasses below mirror its ``$defs`` one-to-one and are
(de)serialised generically from their field definitions, so adding a field is a
schema + dataclass change, never a new branch in a serializer.

Conventions (see the schema description for the normative text): km, km/s,
degrees, seconds; non-rotating Earth-centred inertial frame fixed at epoch;
``epoch_utc`` is ISO 8601 UTC; ``simulation_time_s`` is seconds since epoch.
"""

from __future__ import annotations

import dataclasses
import json
import types
import typing
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, ClassVar

from .validation import SchemaValidator

SCHEMA_PATH = Path(__file__).with_name("data") / "simulation_contract.schema.json"
SCHEMA: dict[str, Any] = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
SCHEMA_VERSION: str = SCHEMA["x-schema-version"]
VALIDATOR = SchemaValidator(SCHEMA)

Vector3 = typing.Tuple[float, float, float]


class ContractError(Exception):
    """A payload violates the contract. ``errors`` lists field-path diagnostics."""

    def __init__(self, errors: list[dict[str, str]]):
        self.errors = errors
        super().__init__("contract violation: " + "; ".join(f"{e['path']}: {e['message']}" for e in errors))


def parse_version(version: str) -> tuple[int, int, int]:
    major, minor, patch = version.split(".")
    return int(major), int(minor), int(patch)


def is_compatible_version(version: Any) -> bool:
    """Same major as the supported schema and a minor not newer than ours."""
    if not isinstance(version, str):
        return False
    try:
        major, minor, _ = parse_version(version)
    except ValueError:
        return False
    ours = parse_version(SCHEMA_VERSION)
    return major == ours[0] and minor <= ours[1]


def _version_error(payload: Any) -> list[dict[str, str]]:
    if not isinstance(payload, dict) or "schema_version" not in payload:
        return []
    version = payload["schema_version"]
    if is_compatible_version(version):
        return []
    return [{
        "path": "$.schema_version",
        "message": f"incompatible schema version {version!r}; this core supports {SCHEMA_VERSION}",
    }]


def validate_payload(payload: Any, definition: str) -> None:
    """Raise ContractError unless ``payload`` is a valid ``$defs/<definition>``."""
    errors = _version_error(payload) or VALIDATOR.validate(payload, f"#/$defs/{definition}")
    if errors:
        raise ContractError(errors)


# --- generic (de)serialisation -------------------------------------------------

_MISSING = dataclasses.MISSING


def _field_type(hint: Any) -> tuple[Any, bool]:
    """Return (inner_type, optional) for ``X | None`` style hints."""
    origin = typing.get_origin(hint)
    if origin is typing.Union or origin is types.UnionType:
        args = [a for a in typing.get_args(hint) if a is not type(None)]
        if len(args) == 1:
            return args[0], True
    return hint, False


def _from_json(hint: Any, value: Any) -> Any:
    hint, _ = _field_type(hint)
    origin = typing.get_origin(hint)
    if dataclasses.is_dataclass(hint):
        return hint.from_dict(value)
    if origin in (list, typing.List):
        (item_type,) = typing.get_args(hint)
        return [_from_json(item_type, v) for v in value]
    if origin in (tuple, typing.Tuple):
        return tuple(float(v) for v in value)
    if hint is float:
        return float(value)
    return value


def _to_json(value: Any) -> Any:
    if dataclasses.is_dataclass(value):
        return value.to_dict()
    if isinstance(value, (list, tuple)):
        return [_to_json(v) for v in value]
    return value


class ContractModel:
    """Mixin giving dataclasses schema-backed ``from_dict``/``to_dict``."""

    DEFINITION: ClassVar[str]

    @classmethod
    def from_dict(cls, payload: Any):
        validate_payload(payload, cls.DEFINITION)
        hints = typing.get_type_hints(cls)
        kwargs: dict[str, Any] = {}
        for f in fields(cls):
            if f.name in payload:
                kwargs[f.name] = _from_json(hints[f.name], payload[f.name])
        return cls(**kwargs)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for f in fields(self):
            value = getattr(self, f.name)
            if value is None:
                continue
            out[f.name] = _to_json(value)
        return out

    @classmethod
    def from_json(cls, data: bytes | str):
        try:
            payload = json.loads(data)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ContractError([{"path": "$", "message": f"invalid JSON: {exc}"}]) from exc
        return cls.from_dict(payload)

    def to_json(self, **kwargs: Any) -> str:
        return json.dumps(self.to_dict(), **kwargs)


# --- the contract types ---------------------------------------------------------

@dataclass(frozen=True)
class VersionMetadata(ContractModel):
    DEFINITION: ClassVar[str] = "VersionMetadata"
    name: str
    version: str


@dataclass(frozen=True)
class OrbitElements(ContractModel):
    DEFINITION: ClassVar[str] = "OrbitElements"
    semi_major_axis_km: float
    eccentricity: float
    inclination_deg: float
    raan_deg: float
    argument_of_perigee_deg: float
    true_anomaly_deg: float


@dataclass(frozen=True)
class SimulationClock(ContractModel):
    DEFINITION: ClassVar[str] = "SimulationClock"
    epoch_utc: str
    simulation_time_s: float
    time_scale: float
    paused: bool


@dataclass(frozen=True)
class ComponentConfig(ContractModel):
    """Day 18: one virtual component a satellite runs (configuration)."""
    DEFINITION: ClassVar[str] = "ComponentConfig"
    type: str
    parameters: dict[str, Any] | None = None


@dataclass(frozen=True)
class SatelliteComponentState(ContractModel):
    """Day 18: runtime state of one component in a snapshot."""
    DEFINITION: ClassVar[str] = "SatelliteComponentState"
    type: str
    state: dict[str, Any] | None = None


@dataclass(frozen=True)
class SatelliteConfig(ContractModel):
    DEFINITION: ClassVar[str] = "SatelliteConfig"
    id: str
    orbit: OrbitElements
    name: str | None = None
    components: list[ComponentConfig] | None = None  # Day 18/20

    @property
    def label(self) -> str:
        return self.name or self.id


@dataclass(frozen=True)
class SimulationConfig(ContractModel):
    DEFINITION: ClassVar[str] = "SimulationConfig"
    schema_version: str
    scenario_id: str
    seed: int
    epoch_utc: str
    satellites: list[SatelliteConfig] = field(default_factory=list)
    name: str | None = None
    time_scale: float = 1.0
    # Day 15: registered dynamics component; None means the default model.
    dynamics_model: str | None = None
    # Day 18/20: fleet-wide default components for satellites that declare none.
    components: list[ComponentConfig] | None = None

    @property
    def label(self) -> str:
        return self.name or self.scenario_id

    def initial_clock(self) -> SimulationClock:
        return SimulationClock(epoch_utc=self.epoch_utc, simulation_time_s=0.0, time_scale=self.time_scale, paused=True)


@dataclass(frozen=True)
class SatelliteState(ContractModel):
    DEFINITION: ClassVar[str] = "SatelliteState"
    id: str
    position_eci_km: Vector3
    velocity_eci_km_s: Vector3
    orbit: OrbitElements | None = None
    components: list[SatelliteComponentState] | None = None  # Day 18/20


@dataclass(frozen=True)
class SimulationSnapshot(ContractModel):
    DEFINITION: ClassVar[str] = "SimulationSnapshot"
    schema_version: str
    scenario_id: str
    producer: VersionMetadata
    clock: SimulationClock
    satellites: list[SatelliteState] = field(default_factory=list)


DEFINITIONS: dict[str, type[ContractModel]] = {
    cls.DEFINITION: cls
    for cls in (VersionMetadata, OrbitElements, SimulationClock, SatelliteConfig,
                SimulationConfig, SatelliteState, SimulationSnapshot,
                ComponentConfig, SatelliteComponentState)
}
