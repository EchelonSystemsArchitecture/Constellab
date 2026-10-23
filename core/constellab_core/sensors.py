"""Day 26: sensor footprint and observation-opportunity models.

A satellite can only see a target when the geometry works *and* the sensor can
turn the look into a usable observation. Those are two different questions and
this module keeps them apart:

* **geometry** — is the target above the horizon, inside the field of regard,
  within range and not occulted by the Earth?
* **quality** — given that geometry, is the resulting product good enough:
  resolution proxy, off-nadir obliquity, a deterministic cloud mask, and the
  sensor's own availability windows (a duty cycle, not always-on).

Sensor behaviour lives behind a :class:`SensorModel` plugin registry. A scenario
selects a registered model and parameter values; the model's numbers come from
the Day 19 parameter registry (``sensor.conical``) merged with the model's own
declared defaults, so adding a sensor model is a registration, not a core edit.

Everything here is a **model of a model**: a pointing cone, a resolution proxy
computed from slant range, a hash-based weather mask. No image is acquired and
no real instrument is simulated. The declared ``fidelity`` string is part of the
payload so a consumer can not mistake this for mission-grade sensor modelling.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Protocol, Sequence, runtime_checkable

from .frames import (
    EARTH_EQUATORIAL_RADIUS_KM,
    GeodeticPoint,
    eci_to_ecef,
    geodetic_from_ecef,
)

Vector3 = tuple[float, float, float]

SENSOR_MODEL_VERSION = "sensor-models-1"

FIDELITY = (
    "conical field-of-regard around the boresight; spherical Earth for horizon and occlusion",
    "resolution is a slant-range proxy (resolution_at_nadir_m scaled by range ratio and obliquity)",
    "cloud mask is a deterministic hash of (seed, target, time bucket), not a weather model",
    "sensor availability is a fixed duty-cycle schedule, not a real instrument timeline",
)


class SensorError(ValueError):
    """A sensor model, its configuration or a geometry query is invalid."""


def _finite(name: str, value: Any) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(float(value)):
        raise SensorError(f"{name} must be a finite number, got {value!r}")
    return float(value)


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _dot(a: Vector3, b: Vector3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _sub(a: Vector3, b: Vector3) -> Vector3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _norm(v: Vector3) -> float:
    return math.sqrt(_dot(v, v))


def _unit(v: Vector3) -> Vector3:
    n = _norm(v)
    if n <= 0.0:
        raise SensorError("zero-length direction vector")
    return (v[0] / n, v[1] / n, v[2] / n)


def _angle_deg(a: Vector3, b: Vector3) -> float:
    """Angle between two vectors in degrees (numerically clamped)."""
    cosine = _dot(_unit(a), _unit(b))
    return math.degrees(math.acos(max(-1.0, min(1.0, cosine))))


# --- deterministic weather mask ----------------------------------------------------

CLOUD_BUCKET_S = 900.0


def cloud_fraction(seed: int, target_id: str, time_s: float, maximum: float = 0.7) -> float:
    """Deterministic, slowly-changing cloud cover in ``[0, maximum]``.

    A hash per (seed, target, 15-minute bucket) is not a weather model, but it
    is reproducible, target-specific and time-varying — enough to exercise the
    "geometry is visible but the product is unusable" case on demand.
    """
    bucket = int(math.floor(max(0.0, time_s) / CLOUD_BUCKET_S))
    digest = hashlib.sha256(f"{seed}|{target_id}|{bucket}".encode("utf-8")).hexdigest()
    unit = int(digest[:8], 16) / 0xFFFFFFFF
    return round(unit * max(0.0, maximum), 6)


# --- sensor models -----------------------------------------------------------------

@dataclass(frozen=True)
class SensorConfig:
    """Effective, validated parameters for one sensor on one satellite."""

    model: str
    half_angle_deg: float = 30.0
    max_range_km: float = 2_500.0
    integration_time_s: float = 0.5
    duty_cycle_ratio: float = 0.3
    resolution_at_nadir_m: float = 10.0
    max_off_nadir_deg: float = 45.0
    min_elevation_deg: float = 10.0
    availability_period_s: float = 600.0
    min_quality: float = 0.25
    cloud_max: float = 0.7
    enabled: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.model, str) or not self.model:
            raise SensorError("sensor model key must be a non-empty string")
        if not 0.0 < self.half_angle_deg <= 89.9:
            raise SensorError(f"half_angle_deg must be in (0, 89.9], got {self.half_angle_deg}")
        if self.max_range_km <= 0.0:
            raise SensorError("max_range_km must be positive")
        if self.integration_time_s <= 0.0:
            raise SensorError("integration_time_s must be positive")
        if not 0.0 <= self.duty_cycle_ratio <= 1.0:
            raise SensorError("duty_cycle_ratio must be within [0, 1]")
        if self.resolution_at_nadir_m <= 0.0:
            raise SensorError("resolution_at_nadir_m must be positive")
        if not 0.0 <= self.max_off_nadir_deg <= 89.9:
            raise SensorError("max_off_nadir_deg must be within [0, 89.9]")
        if not 0.0 <= self.min_elevation_deg <= 90.0:
            raise SensorError("min_elevation_deg must be within [0, 90]")
        if self.availability_period_s <= 0.0:
            raise SensorError("availability_period_s must be positive")
        if not 0.0 <= self.min_quality <= 1.0:
            raise SensorError("min_quality must be within [0, 1]")

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "half_angle_deg": self.half_angle_deg,
            "max_range_km": self.max_range_km,
            "integration_time_s": self.integration_time_s,
            "duty_cycle_ratio": self.duty_cycle_ratio,
            "resolution_at_nadir_m": self.resolution_at_nadir_m,
            "max_off_nadir_deg": self.max_off_nadir_deg,
            "min_elevation_deg": self.min_elevation_deg,
            "availability_period_s": self.availability_period_s,
            "min_quality": self.min_quality,
            "cloud_max": self.cloud_max,
            "enabled": self.enabled,
        }


@runtime_checkable
class SensorModel(Protocol):
    """A sensor footprint model selected by key, never branched on in the loop."""

    key: str
    label: str
    fidelity: tuple[str, ...]
    defaults: Mapping[str, Any]

    def config(self, values: Mapping[str, Any] | None = None, *, seed: int = 0) -> SensorConfig:
        """Merge model defaults, registry values and scenario overrides."""

    def is_available(self, config: SensorConfig, time_s: float) -> bool:
        """Whether the instrument can acquire at ``time_s`` (duty cycle)."""


class _BaseSensor:
    """Shared config merging; subclasses only declare their geometry defaults."""

    key = "sensor.base"
    label = "Sensor"
    fidelity = FIDELITY
    defaults: dict[str, Any] = {}

    def config(self, values: Mapping[str, Any] | None = None, *, seed: int = 0) -> SensorConfig:
        from .parameters import builtin_registry

        merged: dict[str, Any] = dict(self.defaults)
        registry = builtin_registry()
        if self.key in registry.owners():
            # Registry defaults + validation (types, bounds, unknown keys).
            merged.update(registry.effective_values(self.key, values or {}))
        elif values:
            merged.update(values)
        merged["model"] = self.key
        merged.setdefault("seed", seed)
        known = set(SensorConfig.__dataclass_fields__)
        filtered = {k: v for k, v in merged.items() if k in known}
        for numeric in (
            "half_angle_deg", "max_range_km", "integration_time_s", "duty_cycle_ratio",
            "resolution_at_nadir_m", "max_off_nadir_deg", "min_elevation_deg",
            "availability_period_s", "min_quality", "cloud_max",
        ):
            if numeric in filtered:
                filtered[numeric] = _finite(numeric, filtered[numeric])
        if "enabled" in filtered:
            filtered["enabled"] = bool(filtered["enabled"])
        return SensorConfig(**filtered)

    def is_available(self, config: SensorConfig, time_s: float) -> bool:
        if not config.enabled:
            return False
        if config.duty_cycle_ratio >= 1.0:
            return True
        if config.duty_cycle_ratio <= 0.0:
            return False
        period = config.availability_period_s
        phase = (max(0.0, time_s) % period) / period
        return phase < config.duty_cycle_ratio


class ConicalNadirSensor(_BaseSensor):
    """Nadir-pointing conical sensor: the field of regard sits under the satellite."""

    key = "sensor.conical"
    label = "Conical nadir sensor"
    defaults = {
        "half_angle_deg": 30.0,
        "max_range_km": 2_500.0,
        "resolution_at_nadir_m": 10.0,
        "max_off_nadir_deg": 30.0,
        "min_elevation_deg": 10.0,
        "availability_period_s": 600.0,
        "min_quality": 0.25,
    }


class AgilePointingSensor(_BaseSensor):
    """Slewing sensor: larger off-nadir envelope, coarser per-frame resolution."""

    key = "sensor.agile"
    label = "Agile pointing sensor"
    defaults = {
        "half_angle_deg": 15.0,
        "max_range_km": 3_000.0,
        "resolution_at_nadir_m": 25.0,
        "max_off_nadir_deg": 55.0,
        "min_elevation_deg": 5.0,
        "availability_period_s": 1_200.0,
        "min_quality": 0.2,
    }


_REGISTRY: dict[str, SensorModel] = {}


def register_sensor_model(model: SensorModel) -> SensorModel:
    key = getattr(model, "key", None)
    if not isinstance(key, str) or not key:
        raise SensorError("a sensor model must declare a non-empty string key")
    if key in _REGISTRY:
        raise SensorError(f"sensor model {key!r} is already registered")
    _REGISTRY[key] = model
    return model


def unregister_sensor_model(key: str) -> SensorModel | None:
    return _REGISTRY.pop(key, None)


def sensor_model(key: str) -> SensorModel:
    try:
        return _REGISTRY[key]
    except KeyError:
        raise SensorError(
            f"unknown sensor model {key!r}; registered models: {', '.join(sorted(_REGISTRY)) or '(none)'}"
        ) from None


def registered_sensor_models() -> tuple[str, ...]:
    return tuple(sorted(_REGISTRY))


def sensor_models_payload() -> dict[str, Any]:
    return {
        "version": SENSOR_MODEL_VERSION,
        "fidelity": list(FIDELITY),
        "models": [
            {
                "key": key,
                "label": model.label,
                "defaults": dict(model.defaults),
                "fidelity": list(model.fidelity),
            }
            for key, model in sorted(_REGISTRY.items())
        ],
    }


for _model in (ConicalNadirSensor(), AgilePointingSensor()):
    register_sensor_model(_model)


# --- geometry ----------------------------------------------------------------------

@dataclass(frozen=True)
class Geometry:
    """Instantaneous line-of-sight geometry between one satellite and one target."""

    time_s: float
    range_km: float
    elevation_deg: float
    off_nadir_deg: float
    altitude_km: float
    occulted: bool
    in_cone: bool
    in_range: bool
    resolution_m: float

    @property
    def visible(self) -> bool:
        """Geometric visibility alone — quality and availability are separate."""
        return (not self.occulted) and self.in_cone and self.in_range

    def to_dict(self) -> dict[str, Any]:
        return {
            "time_s": self.time_s,
            "range_km": round(self.range_km, 6),
            "elevation_deg": round(self.elevation_deg, 6),
            "off_nadir_deg": round(self.off_nadir_deg, 6),
            "altitude_km": round(self.altitude_km, 6),
            "occulted": self.occulted,
            "in_cone": self.in_cone,
            "in_range": self.in_range,
            "resolution_m": round(self.resolution_m, 6),
            "visible": self.visible,
        }


def _segment_clears_earth(a: Vector3, b: Vector3, time_s: float = 0.0) -> bool:
    """True when the a→b segment stays at or above the WGS-84 surface.

    Earth clearance is measured as a geodetic altitude, not a sphere radius: a
    ground target at 37° latitude sits ~11 km below the equatorial radius, and
    treating it as "inside the Earth" would make every mid-latitude target
    permanently occulted.
    """
    ab = _sub(b, a)
    denom = _dot(ab, ab)
    if denom <= 0.0:
        return True
    t = _clamp(-_dot(a, ab) / denom, 0.0, 1.0)
    closest = (a[0] + ab[0] * t, a[1] + ab[1] * t, a[2] + ab[2] * t)
    altitude = geodetic_from_ecef(eci_to_ecef(closest, 0.0, time_s)).altitude_km
    # A grazing pass touches the surface exactly; keep that visible.
    return altitude >= -1e-6


def target_eci(target: Any, time_s: float) -> Vector3:
    """Target ground position in ECI at ``time_s`` (altitude 0 above the ellipsoid)."""
    return GeodeticPoint(target.lat_deg, target.lon_deg, 0.0).to_eci(time_s)


def observation_geometry(
    satellite_position_km: Vector3,
    target_position_km: Vector3,
    config: SensorConfig,
    *,
    time_s: float = 0.0,
) -> Geometry:
    """Footprint geometry for one satellite/target pair at one instant."""
    offset = _sub(target_position_km, satellite_position_km)
    distance = _norm(offset)
    if distance <= 0.0:
        raise SensorError("satellite and target coincide; geometry is undefined")
    altitude = _norm(satellite_position_km) - EARTH_EQUATORIAL_RADIUS_KM
    nadir = (-satellite_position_km[0], -satellite_position_km[1], -satellite_position_km[2])
    off_nadir = _angle_deg(nadir, offset)
    up = _unit(target_position_km)
    # Elevation is measured at the target, towards the satellite.
    to_satellite = (-offset[0], -offset[1], -offset[2])
    elevation = 90.0 - _angle_deg(up, to_satellite)
    in_cone = off_nadir <= min(config.half_angle_deg, config.max_off_nadir_deg)
    in_range = distance <= config.max_range_km
    occulted = not _segment_clears_earth(satellite_position_km, target_position_km, time_s)
    # Slant-range resolution proxy: nadir resolution scaled by the range ratio and
    # by how obliquely the footprint is seen. Floored at the nadir value.
    ratio = max(1.0, distance / max(altitude, 1.0))
    obliquity = max(0.2, math.cos(math.radians(off_nadir)))
    resolution_m = config.resolution_at_nadir_m * ratio / obliquity
    return Geometry(
        time_s=float(time_s),
        range_km=distance,
        elevation_deg=max(-90.0, elevation),
        off_nadir_deg=off_nadir,
        altitude_km=altitude,
        occulted=occulted,
        in_cone=in_cone,
        in_range=in_range,
        resolution_m=resolution_m,
    )


def quality_score(geometry: Geometry, config: SensorConfig, *, cloud: float) -> float:
    """Usable-product score in ``[0, 1]`` from geometry, resolution and cloud."""
    if not geometry.visible:
        return 0.0
    range_margin = 1.0 - (geometry.range_km / config.max_range_km)
    cone_margin = 1.0 - (geometry.off_nadir_deg / max(config.half_angle_deg, 1e-9))
    obliquity = 1.0 - 0.4 * _clamp(geometry.off_nadir_deg / 90.0)
    resolution = _clamp(config.resolution_at_nadir_m / max(geometry.resolution_m, 1e-9))
    clear = 1.0 - _clamp(cloud / max(config.cloud_max, 1e-9))
    return _clamp(
        0.25 * _clamp(range_margin)
        + 0.15 * _clamp(cone_margin)
        + 0.20 * resolution
        + 0.15 * obliquity * clear
        + 0.25 * clear
    )


# --- access windows -----------------------------------------------------------------

@dataclass
class Sample:
    time_s: float
    geometry: Geometry
    cloud: float
    quality: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "time_s": self.time_s,
            "geometry": self.geometry.to_dict(),
            "cloud": self.cloud,
            "quality": round(self.quality, 6),
        }


@dataclass
class AccessWindow:
    """One contiguous geometrically-visible interval for a satellite/target pair."""

    satellite_id: str
    target_id: str
    model: str
    start_s: float
    end_s: float
    peak_quality: float
    mean_quality: float
    best_resolution_m: float
    samples: list[Sample] = field(default_factory=list)
    usable: bool = False
    reasons: list[str] = field(default_factory=list)

    @property
    def duration_s(self) -> float:
        return self.end_s - self.start_s

    def to_dict(self, *, include_samples: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "satellite_id": self.satellite_id,
            "target_id": self.target_id,
            "model": self.model,
            "start_s": round(self.start_s, 6),
            "end_s": round(self.end_s, 6),
            "duration_s": round(self.duration_s, 6),
            "peak_quality": round(self.peak_quality, 6),
            "mean_quality": round(self.mean_quality, 6),
            "best_resolution_m": round(self.best_resolution_m, 6),
            "usable": self.usable,
            "reasons": list(self.reasons),
        }
        if include_samples:
            payload["samples"] = [sample.to_dict() for sample in self.samples]
        return payload


def _window_reasons(window: AccessWindow, target: Any, config: SensorConfig,
                    available: bool) -> list[str]:
    reasons: list[str] = []
    requirements = getattr(target, "requirements", {}) or {}
    if not config.enabled:
        reasons.append("sensor disabled")
    if not available:
        reasons.append("sensor unavailable (duty cycle)")
    if window.peak_quality < config.min_quality:
        reasons.append(f"quality {window.peak_quality:.3f} below min_quality {config.min_quality:.3f}")
    min_resolution = requirements.get("min_resolution_m")
    if min_resolution is not None and window.best_resolution_m > float(min_resolution):
        reasons.append(
            f"best resolution {window.best_resolution_m:.1f} m coarser than required {float(min_resolution):.1f} m"
        )
    min_confidence = requirements.get("min_confidence")
    if min_confidence is not None and window.peak_quality < float(min_confidence):
        reasons.append(
            f"quality {window.peak_quality:.3f} below target requirement {float(min_confidence):.3f}"
        )
    return reasons


def access_windows(
    satellite_id: str,
    satellite_orbit: Any,
    target: Any,
    *,
    config: SensorConfig,
    horizon_s: float,
    step_s: float = 30.0,
    seed: int = 0,
    satellite_position: Any = None,
    window_s: tuple[float, float] | None = None,
) -> list[AccessWindow]:
    """Scan ``[0, horizon_s]`` and return one window per contiguous visible run.

    ``satellite_position(time_s) -> Vector3`` may be supplied to decouple this
    from the dynamics registry; otherwise the orbital elements are propagated
    with the regime ``keplerian-two-body`` model, exactly like the simulation.
    ``window_s`` clips the scan to a target's active interval, so an opportunity
    never exists outside the event it would observe.
    """
    if step_s <= 0.0:
        raise SensorError("step_s must be positive")
    if horizon_s < 0.0:
        raise SensorError("horizon_s must be non-negative")
    if satellite_position is None:
        from .dynamics import DEFAULT_MODEL_KEY, dynamics_model

        model = dynamics_model(DEFAULT_MODEL_KEY)
        position_fn = lambda t: model.state_at(satellite_orbit, t)[0]  # noqa: E731
    else:
        position_fn = satellite_position

    windows: list[AccessWindow] = []
    current: list[Sample] = []

    def flush() -> None:
        if not current:
            return
        samples = current[:]
        peak = max(s.quality for s in samples)
        mean = sum(s.quality for s in samples) / len(samples)
        best_resolution = min(s.geometry.resolution_m for s in samples)
        available = any(
            sensor_model(config.model).is_available(config, s.time_s) for s in samples
        )
        window = AccessWindow(
            satellite_id=satellite_id,
            target_id=target.id,
            model=config.model,
            start_s=samples[0].time_s,
            end_s=samples[-1].time_s,
            peak_quality=peak,
            mean_quality=mean,
            best_resolution_m=best_resolution,
            samples=samples,
        )
        window.reasons = _window_reasons(window, target, config, available)
        window.usable = (
            available
            and window.peak_quality >= config.min_quality
            and not window.reasons
        )
        windows.append(window)
        current.clear()

    scan_start, scan_end = 0.0, horizon_s
    if window_s is not None:
        scan_start = max(0.0, float(window_s[0]))
        scan_end = min(horizon_s, float(window_s[1]))
    if scan_end < scan_start:
        return []
    index = int(math.ceil(scan_start / step_s))
    while round(index * step_s, 9) <= scan_end:
        time_s = round(index * step_s, 9)
        satellite_position_km = position_fn(time_s)
        geometry = observation_geometry(
            satellite_position_km,
            target_eci(target, time_s),
            config,
            time_s=time_s,
        )
        if geometry.visible and geometry.elevation_deg >= config.min_elevation_deg:
            cloud = cloud_fraction(seed, target.id, time_s, config.cloud_max)
            current.append(
                Sample(
                    time_s=time_s,
                    geometry=geometry,
                    cloud=cloud,
                    quality=quality_score(geometry, config, cloud=cloud),
                )
            )
        else:
            flush()
        index += 1
    flush()
    return windows


def sensor_config_for(config: Any, satellite: Any, *, seed: int = 0) -> SensorConfig:
    """The effective sensor configuration a satellite actually flies.

    A declared sensor component wins; otherwise the default reference sensor
    (``sensor.conical``) applies with registry defaults. Parameters are read from
    the component declaration, never from a parameter name in the loop.
    """
    from . import components as component_registry

    for declared in component_registry.declared_components(config, satellite):
        try:
            model = component_registry.component(declared.type)
        except component_registry.ComponentError:
            continue
        if getattr(model, "kind", None) != "sensor":
            continue
        try:
            sensor = sensor_model(declared.type)
        except SensorError:
            continue
        values = declared.parameters or {}
        return sensor.config(values, seed=seed)
    return sensor_model("sensor.conical").config({}, seed=seed)


def opportunity_windows(
    config: Any,
    targets: Sequence[Any],
    *,
    horizon_s: float,
    step_s: float = 30.0,
    seed: int = 0,
) -> tuple[list[AccessWindow], dict[str, SensorConfig]]:
    """Access window objects and the effective sensor config per satellite."""
    windows: list[AccessWindow] = []
    sensors: dict[str, SensorConfig] = {}
    for satellite in sorted(config.satellites, key=lambda s: s.id):
        sensor = sensor_config_for(config, satellite, seed=seed)
        sensors[satellite.id] = sensor
        for target in sorted(targets, key=lambda t: t.id):
            windows.extend(
                access_windows(
                    satellite.id,
                    satellite.orbit,
                    target,
                    config=sensor,
                    horizon_s=horizon_s,
                    step_s=step_s,
                    seed=seed,
                    window_s=(target.start_s, target.end_s),
                )
            )
    return windows, sensors


def build_opportunities(
    config: Any,
    targets: Sequence[Any],
    *,
    horizon_s: float,
    step_s: float = 30.0,
    seed: int = 0,
    include_samples: bool = False,
) -> dict[str, Any]:
    """Access windows for every satellite/target pair, in stable id order.

    The result is a plan an operator or policy can read: it carries timing and
    quality/resource metadata, and it is deterministic in
    ``(config, targets, horizon_s, step_s, seed)``.
    """
    windows, sensors = opportunity_windows(
        config, targets, horizon_s=horizon_s, step_s=step_s, seed=seed
    )
    usable = [w for w in windows if w.usable]
    return {
        "version": SENSOR_MODEL_VERSION,
        "fidelity": list(FIDELITY),
        "horizon_s": horizon_s,
        "step_s": step_s,
        "seed": seed,
        "sensors": {sid: sensor.to_dict() for sid, sensor in sensors.items()},
        "window_count": len(windows),
        "usable_window_count": len(usable),
        "targets": sorted({w.target_id for w in windows}),
        "windows": [w.to_dict(include_samples=include_samples) for w in windows],
    }


def next_usable_window(
    windows: Iterable[AccessWindow], *, after_s: float, target_id: str | None = None
) -> AccessWindow | None:
    """Earliest usable window ending at or after ``after_s`` (stable order)."""
    candidates = [
        w for w in windows
        if w.usable and w.end_s >= after_s and (target_id is None or w.target_id == target_id)
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda w: (w.start_s, w.satellite_id, w.target_id))
