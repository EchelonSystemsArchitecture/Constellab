"""Keplerian elements -> Earth-centred inertial state (illustrative two-body model).

Converts the elements declared in a ``SimulationConfig`` into the Cartesian
state carried by a ``SimulationSnapshot`` at the scenario epoch. There is no
time propagation yet (that is the Day 3+ engine); this exists so the frontend
consumes core-produced positions from day one instead of computing its own.

Assumptions: point-mass Earth, mu = 398600.4418 km^3/s^2, no perturbations,
non-rotating ECI frame fixed at epoch. Values are illustrative, not mission grade.
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


def _rot_z(v: Vector3, angle: float) -> Vector3:
    c, s = math.cos(angle), math.sin(angle)
    return (c * v[0] - s * v[1], s * v[0] + c * v[1], v[2])


def _rot_x(v: Vector3, angle: float) -> Vector3:
    c, s = math.cos(angle), math.sin(angle)
    return (v[0], c * v[1] - s * v[2], s * v[1] + c * v[2])


def _perifocal_to_eci(v: Vector3, elements: OrbitElements) -> Vector3:
    v = _rot_z(v, math.radians(elements.argument_of_perigee_deg))
    v = _rot_x(v, math.radians(elements.inclination_deg))
    return _rot_z(v, math.radians(elements.raan_deg))


def state_from_elements(elements: OrbitElements) -> tuple[Vector3, Vector3]:
    """Return (position_km, velocity_km_s) in ECI for the given elements at epoch."""
    a, e = elements.semi_major_axis_km, elements.eccentricity
    nu = math.radians(elements.true_anomaly_deg)
    p = a * (1.0 - e * e)
    r = p / (1.0 + e * math.cos(nu))
    position_pf: Vector3 = (r * math.cos(nu), r * math.sin(nu), 0.0)
    k = math.sqrt(MU_EARTH_KM3_S2 / p)
    velocity_pf: Vector3 = (-k * math.sin(nu), k * (e + math.cos(nu)), 0.0)
    return _perifocal_to_eci(position_pf, elements), _perifocal_to_eci(velocity_pf, elements)


def mean_motion_rad_s(elements: OrbitElements) -> float:
    """Mean motion n = sqrt(mu / a^3) in rad/s."""
    return math.sqrt(MU_EARTH_KM3_S2 / elements.semi_major_axis_km ** 3)


def orbital_period_s(elements: OrbitElements) -> float:
    return 2.0 * math.pi * math.sqrt(elements.semi_major_axis_km ** 3 / MU_EARTH_KM3_S2)


def true_anomaly_at_time(elements: OrbitElements, time_s: float) -> float:
    """Compute true anomaly (degrees) at given simulation time (seconds since epoch).

    Uses Kepler's equation for elliptical orbits:
    M = M0 + n * t
    E = M + e * sin(E)  (solved iteratively)
    nu = 2 * atan2(sqrt(1+e)*sin(E/2), sqrt(1-e)*cos(E/2))
    """
    a, e = elements.semi_major_axis_km, elements.eccentricity
    n = mean_motion_rad_s(elements)
    M0 = math.radians(elements.true_anomaly_deg)  # At epoch, true anomaly = mean anomaly for circular
    if e > 1e-10:
        # For non-circular, we'd need to convert true anomaly to eccentric anomaly
        # For Day 5, use simplified circular approximation: M = nu for e=0
        M0 = math.radians(elements.true_anomaly_deg)

    M = M0 + n * time_s
    M = M % (2 * math.pi)

    if e < 1e-10:
        # Circular orbit: true anomaly = mean anomaly
        nu = M
    else:
        # Solve Kepler's equation: E = M + e * sin(E)
        E = M
        for _ in range(10):
            E = M + e * math.sin(E)
        # Convert eccentric anomaly to true anomaly
        nu = 2 * math.atan2(
            math.sqrt(1 + e) * math.sin(E / 2),
            math.sqrt(1 - e) * math.cos(E / 2)
        )

    return math.degrees(nu)


def state_from_elements_at_time(elements: OrbitElements, time_s: float) -> tuple[Vector3, Vector3]:
    """Return (position_km, velocity_km_s) in ECI for the given elements at simulation time."""
    nu_deg = true_anomaly_at_time(elements, time_s)
    a, e = elements.semi_major_axis_km, elements.eccentricity
    nu = math.radians(nu_deg)
    p = a * (1.0 - e * e)
    r = p / (1.0 + e * math.cos(nu))
    position_pf: Vector3 = (r * math.cos(nu), r * math.sin(nu), 0.0)
    k = math.sqrt(MU_EARTH_KM3_S2 / p)
    velocity_pf: Vector3 = (-k * math.sin(nu), k * (e + math.cos(nu)), 0.0)
    return _perifocal_to_eci(position_pf, elements), _perifocal_to_eci(velocity_pf, elements)


def initial_snapshot(config: SimulationConfig) -> SimulationSnapshot:
    """Snapshot of ``config`` at simulation_time_s = 0 (the epoch), paused."""
    satellites = []
    for sat in config.satellites:
        position, velocity = state_from_elements(sat.orbit)
        satellites.append(SatelliteState(
            id=sat.id,
            position_eci_km=tuple(round(x, 6) for x in position),
            velocity_eci_km_s=tuple(round(x, 9) for x in velocity),
            orbit=sat.orbit,
        ))
    return SimulationSnapshot(
        schema_version=SCHEMA_VERSION,
        scenario_id=config.scenario_id,
        producer=VersionMetadata(name="constellab-core", version=__version__),
        clock=config.initial_clock(),
        satellites=satellites,
    )


def snapshot_at_time(config: SimulationConfig, time_s: float) -> SimulationSnapshot:
    """Snapshot of ``config`` at the given simulation time (seconds since epoch)."""
    satellites = []
    for sat in config.satellites:
        position, velocity = state_from_elements_at_time(sat.orbit, time_s)
        satellites.append(SatelliteState(
            id=sat.id,
            position_eci_km=tuple(round(x, 6) for x in position),
            velocity_eci_km_s=tuple(round(x, 9) for x in velocity),
            orbit=sat.orbit,
        ))
    base_clock = config.initial_clock()
    return SimulationSnapshot(
        schema_version=SCHEMA_VERSION,
        scenario_id=config.scenario_id,
        producer=VersionMetadata(name="constellab-core", version=__version__),
        clock=SimulationClock(
            epoch_utc=base_clock.epoch_utc,
            simulation_time_s=time_s,
            time_scale=base_clock.time_scale,
            paused=base_clock.paused,
        ),
        satellites=satellites,
    )