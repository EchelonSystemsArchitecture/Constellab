"""Day 17: independent numerical reference for the analytic propagator.

The production model evaluates a closed-form Kepler solution: solve Kepler's
equation for the mean anomaly, convert to true anomaly, evaluate the conic, then
rotate the perifocal frame. That is fast and exactly periodic, but a bug in any
one step (a sign in a rotation, a degree/radian mix-up) would still produce
smooth, plausible motion.

This module provides a deliberately different route: fixed-step classical
Runge-Kutta 4 integration of the two-body acceleration ``-mu r / |r|^3``. It
never solves Kepler's equation and never touches true anomaly, so agreement
between the two is meaningful evidence. It is also the reference used to
generate the checked-in golden trajectories, which freeze the expected numbers
so a later change to either implementation can not silently move the target.

The integrator is not used by the running simulation. It exists for tests and
for comparison evidence, and its own error is documented through the step size
recorded in each golden case.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Sequence

from .contract import OrbitElements
from .frames import MU_EARTH_KM3_S2
from .orbit import state_from_elements_at_time

Vector3 = tuple[float, float, float]


@dataclass(frozen=True)
class TrajectorySample:
    time_s: float
    position_km: Vector3
    velocity_km_s: Vector3

    def to_dict(self) -> dict[str, object]:
        return {
            "time_s": self.time_s,
            "position_km": list(self.position_km),
            "velocity_km_s": list(self.velocity_km_s),
        }


def acceleration(position_km: Vector3, mu: float = MU_EARTH_KM3_S2) -> Vector3:
    """Two-body gravitational acceleration ``-mu r / |r|^3`` (km/s^2)."""
    x, y, z = position_km
    r2 = x * x + y * y + z * z
    if r2 == 0.0:
        raise ValueError("acceleration is singular at the Earth's centre")
    factor = -mu / (r2 * math.sqrt(r2))
    return (factor * x, factor * y, factor * z)


def rk4_step(position_km: Vector3, velocity_km_s: Vector3, dt_s: float,
             mu: float = MU_EARTH_KM3_S2) -> tuple[Vector3, Vector3]:
    """One classical RK4 step of the coupled (r, v) two-body system."""
    if dt_s <= 0.0:
        raise ValueError("dt_s must be positive")

    def add(a: Vector3, b: Vector3, scale: float = 1.0) -> Vector3:
        return (a[0] + scale * b[0], a[1] + scale * b[1], a[2] + scale * b[2])

    k1_r = velocity_km_s
    k1_v = acceleration(position_km, mu)
    k2_r = add(velocity_km_s, k1_v, dt_s / 2.0)
    k2_v = acceleration(add(position_km, k1_r, dt_s / 2.0), mu)
    k3_r = add(velocity_km_s, k2_v, dt_s / 2.0)
    k3_v = acceleration(add(position_km, k2_r, dt_s / 2.0), mu)
    k4_r = add(velocity_km_s, k3_v, dt_s)
    k4_v = acceleration(add(position_km, k3_r, dt_s), mu)

    sixth = dt_s / 6.0
    position = tuple(
        p + sixth * (a + 2.0 * b + 2.0 * c + d)
        for p, a, b, c, d in zip(position_km, k1_r, k2_r, k3_r, k4_r)
    )
    velocity = tuple(
        v + sixth * (a + 2.0 * b + 2.0 * c + d)
        for v, a, b, c, d in zip(velocity_km_s, k1_v, k2_v, k3_v, k4_v)
    )
    return position, velocity  # type: ignore[return-value]


def propagate(
    position_km: Vector3,
    velocity_km_s: Vector3,
    times_s: Sequence[float],
    *,
    max_step_s: float = 5.0,
    mu: float = MU_EARTH_KM3_S2,
) -> list[TrajectorySample]:
    """Integrate from the state at ``times_s[0]`` to every later time.

    Each interval is split into equal sub-steps no larger than ``max_step_s`` so
    the result does not depend on how the caller spaced the sample times. The
    number of sub-steps is recorded implicitly by ``max_step_s``; golden cases
    store it, so their tolerances are justified rather than guessed.
    """
    if max_step_s <= 0.0:
        raise ValueError("max_step_s must be positive")
    times = list(times_s)
    if not times:
        return []
    if any(b < a for a, b in zip(times, times[1:])):
        raise ValueError("times_s must be sorted ascending")

    position, velocity = position_km, velocity_km_s
    samples = [TrajectorySample(times[0], position, velocity)]
    for previous, current in zip(times, times[1:]):
        interval = current - previous
        if interval == 0.0:
            samples.append(TrajectorySample(current, position, velocity))
            continue
        steps = max(1, math.ceil(interval / max_step_s))
        dt = interval / steps
        for _ in range(steps):
            position, velocity = rk4_step(position, velocity, dt, mu)
        samples.append(TrajectorySample(current, position, velocity))
    return samples


def sample_kepler(elements: OrbitElements, times_s: Iterable[float]) -> list[TrajectorySample]:
    """The analytic model's samples at the same instants, for comparison."""
    samples = []
    for time_s in times_s:
        position, velocity = state_from_elements_at_time(elements, time_s)
        samples.append(TrajectorySample(time_s, position, velocity))
    return samples


def _norm(v: Vector3) -> float:
    return math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])


@dataclass(frozen=True)
class TrajectoryComparison:
    """Worst-case deviation between two sampled trajectories."""

    max_position_km: float
    max_velocity_km_s: float
    worst_time_s: float
    tolerance_km: float
    tolerance_km_s: float

    @property
    def ok(self) -> bool:
        return self.max_position_km <= self.tolerance_km and self.max_velocity_km_s <= self.tolerance_km_s

    def to_dict(self) -> dict[str, object]:
        return {
            "max_position_km": self.max_position_km,
            "max_velocity_km_s": self.max_velocity_km_s,
            "worst_time_s": self.worst_time_s,
            "tolerance_km": self.tolerance_km,
            "tolerance_km_s": self.tolerance_km_s,
            "ok": self.ok,
        }


def compare_trajectories(
    expected: Sequence[TrajectorySample],
    actual: Sequence[TrajectorySample],
    *,
    tolerance_km: float,
    tolerance_km_s: float = 1e-6,
) -> TrajectoryComparison:
    """Compare two sample lists by time stamp, returning the worst deviation."""
    if len(expected) != len(actual):
        raise ValueError(f"sample counts differ: {len(expected)} expected, {len(actual)} actual")
    worst_km = 0.0
    worst_km_s = 0.0
    worst_time = 0.0
    for want, got in zip(expected, actual):
        if abs(want.time_s - got.time_s) > 1e-9:
            raise ValueError(f"sample times differ: {want.time_s} vs {got.time_s}")
        offset = tuple(a - b for a, b in zip(want.position_km, got.position_km))
        position_error = _norm(offset)
        if position_error >= worst_km:
            worst_km = position_error
            worst_km_s = _norm(tuple(a - b for a, b in zip(want.velocity_km_s, got.velocity_km_s)))
            worst_time = want.time_s
    return TrajectoryComparison(worst_km, worst_km_s, worst_time, tolerance_km, tolerance_km_s)


def expected_samples(elements: OrbitElements, times_s: Sequence[float],
                     *, max_step_s: float = 5.0) -> list[TrajectorySample]:
    """Integrate from the elements' epoch state with the numerical reference."""
    position, velocity = state_from_elements_at_time(elements, 0.0)
    # Re-anchor the first sample to t=0 by integrating only forward from epoch.
    return propagate(position, velocity, times_s, max_step_s=max_step_s)
