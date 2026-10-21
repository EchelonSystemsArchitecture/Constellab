"""Keplerian elements -> Earth-centred inertial state (illustrative two-body model).

Converts the elements declared in a ``SimulationConfig`` into the Cartesian
state carried by a ``SimulationSnapshot``. Position is an analytic function of
simulation time (``F(t)``), never an incremental integration, so rendering at
any frame rate yields exactly the same state for the same simulated timestamp.

Assumptions: point-mass Earth, mu = 398600.4418 km^3/s^2, no perturbations,
non-rotating ECI frame fixed at epoch. This is a simplified simulation level,
not mission-grade orbital propagation.
"""

from __future__ import annotations

import math

from . import __version__
from .contract import (
    OrbitElements,
    SatelliteState,
    SimulationClock,
    SimulationConfig,
    SimulationSnapshot,
    Vector3,
    VersionMetadata,
    SCHEMA_VERSION,
)

MU_EARTH_KM3_S2 = 398600.4418
EARTH_RADIUS_KM = 6378.137

# Real-world Earth values
SECONDS_PER_EARTH_SIDEREAL_DAY = 86164.0905  # mean sidereal day, IAU/USNO convention
EARTH_AXIAL_TILT_DEG = 23.44  # obliquity of the ecliptic, WGS 84 / IAU 2006
EARTH_ROTATION_DEG_PER_HOUR = 360.0 / (SECONDS_PER_EARTH_SIDEREAL_DAY / 3600.0)  # 15.041°


def _rot_z(v: Vector3, angle: float) -> Vector3:
    c, s = math.cos(angle), math.sin(angle)
    return (c * v[0] - s * v[1], s * v[0] + c * v[1], v[2])


def _rot_x(v: Vector3, angle: float) -> Vector3:
    c, s = math.cos(angle), math.sin(angle)
    return (v[0], c * v[1] - s * v[2], s * v[1] + c * v[2])


def _perifocal_to_eci(v: Vector3, elements: OrbitElements) -> Vector3:
    """R3(raan) . R1(inclination) . R3(argument of perigee), applied in order."""
    v = _rot_z(v, math.radians(elements.argument_of_perigee_deg))
    v = _rot_x(v, math.radians(elements.inclination_deg))
    return _rot_z(v, math.radians(elements.raan_deg))


def mean_motion_rad_s(elements: OrbitElements) -> float:
    """Mean motion n = sqrt(mu / a^3) in rad/s."""
    return math.sqrt(MU_EARTH_KM3_S2 / elements.semi_major_axis_km ** 3)


def orbital_period_s(elements: OrbitElements) -> float:
    return 2.0 * math.pi * math.sqrt(elements.semi_major_axis_km ** 3 / MU_EARTH_KM3_S2)


def eccentric_anomaly_from_true_anomaly(true_anomaly_rad: float, e: float) -> float:
    """E = 2 atan2(sqrt(1-e) sin(nu/2), sqrt(1+e) cos(nu/2))."""
    return 2.0 * math.atan2(
        math.sqrt(1.0 - e) * math.sin(true_anomaly_rad / 2.0),
        math.sqrt(1.0 + e) * math.cos(true_anomaly_rad / 2.0),
    )


def true_anomaly_from_eccentric_anomaly(eccentric_anomaly_rad: float, e: float) -> float:
    """nu = 2 atan2(sqrt(1+e) sin(E/2), sqrt(1-e) cos(E/2))."""
    return 2.0 * math.atan2(
        math.sqrt(1.0 + e) * math.sin(eccentric_anomaly_rad / 2.0),
        math.sqrt(1.0 - e) * math.cos(eccentric_anomaly_rad / 2.0),
    )


def eccentric_anomaly_from_mean_anomaly(
    mean_anomaly_rad: float, e: float, *, iterations: int = 64, tolerance: float = 1e-13
) -> float:
    """Solve Kepler's equation E - e sin E = M with Newton-Raphson."""
    m = math.remainder(mean_anomaly_rad, 2.0 * math.pi)
    eccentric = m if e < 0.8 else math.pi
    for _ in range(iterations):
        step = (eccentric - e * math.sin(eccentric) - m) / (1.0 - e * math.cos(eccentric))
        eccentric -= step
        if abs(step) <= tolerance:
            break
    return eccentric


def true_anomaly_at_time(elements: OrbitElements, time_s: float) -> float:
    """True anomaly (degrees) at ``time_s`` seconds since the scenario epoch.

    The epoch true anomaly is converted to a mean anomaly before advancing, so
    ``true_anomaly_at_time(elements, 0)`` is exactly ``elements.true_anomaly_deg``.
    """
    e = elements.eccentricity
    epoch_eccentric = eccentric_anomaly_from_true_anomaly(math.radians(elements.true_anomaly_deg), e)
    epoch_mean = epoch_eccentric - e * math.sin(epoch_eccentric)
    mean = epoch_mean + mean_motion_rad_s(elements) * time_s
    eccentric = eccentric_anomaly_from_mean_anomaly(mean, e)
    return math.degrees(true_anomaly_from_eccentric_anomaly(eccentric, e))


def _state_from_true_anomaly(elements: OrbitElements, true_anomaly_rad: float) -> tuple[Vector3, Vector3]:
    a, e = elements.semi_major_axis_km, elements.eccentricity
    p = a * (1.0 - e * e)
    cos_nu, sin_nu = math.cos(true_anomaly_rad), math.sin(true_anomaly_rad)
    r = p / (1.0 + e * cos_nu)
    position_pf: Vector3 = (r * cos_nu, r * sin_nu, 0.0)
    k = math.sqrt(MU_EARTH_KM3_S2 / p)
    velocity_pf: Vector3 = (-k * sin_nu, k * (e + cos_nu), 0.0)
    return _perifocal_to_eci(position_pf, elements), _perifocal_to_eci(velocity_pf, elements)


def state_from_elements(elements: OrbitElements) -> tuple[Vector3, Vector3]:
    """Return (position_km, velocity_km_s) in ECI at the scenario epoch."""
    return _state_from_true_anomaly(elements, math.radians(elements.true_anomaly_deg))


def earth_rotation_angle_rad(time_s: float) -> float:
    """Earth rotation angle (radians) at ``time_s`` seconds since the epoch.

    One full 360° turn takes a mean sidereal day (86 164.0905 s), so this is the
    real-world spin of the planet relative to the inertial frame: an observer on
    the ground sweeps 15.041° of ECI longitude per hour. The ECI frame itself
    does **not** rotate — satellites stay inertial there — so this angle is the
    link between ECI and Earth-fixed (latitude/longitude) coordinates.

    Renderers use it to spin the globe, and ground tracks subtract it to turn an
    inertial longitude into a geographic one.
    """
    return math.remainder((time_s / SECONDS_PER_EARTH_SIDEREAL_DAY) * 2.0 * math.pi, 2.0 * math.pi)


def state_from_elements_at_time(elements: OrbitElements, time_s: float) -> tuple[Vector3, Vector3]:
    """Return (position_km, velocity_km_s) in ECI at ``time_s`` since epoch.

    The inertial frame is fixed at epoch, so only the orbit changes with time;
    the planet's spin is reported separately by :func:`earth_rotation_angle_rad`
    and must not be applied here (that would double-count it in ECI).
    """
    return _state_from_true_anomaly(elements, math.radians(true_anomaly_at_time(elements, time_s)))


def _satellite_states(config: SimulationConfig, time_s: float) -> list[SatelliteState]:
    # Day 15: the state comes from the scenario's registered dynamics component,
    # so a future fidelity level is a registry entry instead of a main-loop edit.
    # Imported here to keep ``dynamics`` free to depend on this module's math.
    from .dynamics import DEFAULT_MODEL_KEY, dynamics_model

    model = dynamics_model(config.dynamics_model or DEFAULT_MODEL_KEY)
    satellites = []
    for sat in config.satellites:
        position, velocity = model.state_at(sat.orbit, time_s)
        satellites.append(SatelliteState(
            id=sat.id,
            position_eci_km=tuple(round(x, 6) for x in position),
            velocity_eci_km_s=tuple(round(x, 9) for x in velocity),
            orbit=sat.orbit,
        ))
    return satellites


def initial_snapshot(config: SimulationConfig) -> SimulationSnapshot:
    """Snapshot of ``config`` at simulation_time_s = 0 (the epoch), paused."""
    return SimulationSnapshot(
        schema_version=SCHEMA_VERSION,
        scenario_id=config.scenario_id,
        producer=VersionMetadata(name="constellab-core", version=__version__),
        clock=config.initial_clock(),
        satellites=_satellite_states(config, 0.0),
    )


def snapshot_at_time(
    config: SimulationConfig, time_s: float, clock: SimulationClock | None = None
) -> SimulationSnapshot:
    """Snapshot of ``config`` at ``time_s``.

    ``clock`` supplies the epoch, time scale and paused flag reported to the
    renderer; when omitted the scenario's initial (paused) clock is used.
    """
    base = clock or config.initial_clock()
    return SimulationSnapshot(
        schema_version=SCHEMA_VERSION,
        scenario_id=config.scenario_id,
        producer=VersionMetadata(name="constellab-core", version=__version__),
        clock=SimulationClock(
            epoch_utc=base.epoch_utc,
            simulation_time_s=time_s,
            time_scale=base.time_scale,
            paused=base.paused,
        ),
        satellites=_satellite_states(config, time_s),
    )
