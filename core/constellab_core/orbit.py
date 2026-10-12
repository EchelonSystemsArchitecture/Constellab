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
    """Return (position_km, velocity_km_s) in ECI for the given elements."""
    a, e = elements.semi_major_axis_km, elements.eccentricity
    nu = math.radians(elements.true_anomaly_deg)
    p = a * (1.0 - e * e)
    r = p / (1.0 + e * math.cos(nu))
    position_pf: Vector3 = (r * math.cos(nu), r * math.sin(nu), 0.0)
    k = math.sqrt(MU_EARTH_KM3_S2 / p)
    velocity_pf: Vector3 = (-k * math.sin(nu), k * (e + math.cos(nu)), 0.0)
    return _perifocal_to_eci(position_pf, elements), _perifocal_to_eci(velocity_pf, elements)


def orbital_period_s(elements: OrbitElements) -> float:
    return 2.0 * math.pi * math.sqrt(elements.semi_major_axis_km ** 3 / MU_EARTH_KM3_S2)


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
