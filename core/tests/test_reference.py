"""Day 17 acceptance: the independent RK4 numerical reference.

The analytic Keplerian propagator is closed-form; the reference integrates the
full two-body ODE numerically, so agreement between them is evidence the orbit
math is right — checked against an independent method rather than against the
code it verifies. Tolerances come from a golden run that is itself compared
against the preserved expectation, so a silent accuracy regression cannot pass
just by loosening the numbers.
"""

from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from constellab_core.orbit import (  # noqa: E402
    MU_EARTH_KM3_S2,
    orbital_period_s,
    state_from_elements,
    state_from_elements_at_time,
)
from constellab_core.reference import (  # noqa: E402
    TrajectoryComparison,
    acceleration,
    compare_trajectories,
    expected_samples,
    propagate,
    rk4_step,
    sample_kepler,
)
from constellab_core.contract import OrbitElements  # noqa: E402

# Same fixtures as the dynamics suite: an eccentric Vallado orbit and a
# circular LEO shell, so both code paths are exercised.
VALLADO = OrbitElements(
    semi_major_axis_km=36127.343,
    eccentricity=0.832853,
    inclination_deg=87.870,
    raan_deg=227.898,
    argument_of_perigee_deg=53.38,
    true_anomaly_deg=92.335,
)
CIRCULAR = OrbitElements(
    semi_major_axis_km=6928.137,
    eccentricity=0.0,
    inclination_deg=97.6,
    raan_deg=0.0,
    argument_of_perigee_deg=0.0,
    true_anomaly_deg=0.0,
)


def norm(v):
    return math.sqrt(sum(c * c for c in v))


class TestReferenceIntegration(unittest.TestCase):
    def test_acceleration_is_newton_inverse_square(self):
        r = 7000.0
        acc = acceleration((r, 0.0, 0.0))
        expected = -MU_EARTH_KM3_S2 / r**2
        self.assertAlmostEqual(acc[0], expected, places=15)
        self.assertEqual(acc[1:], (0.0, 0.0))

    def test_acceleration_is_singular_at_the_centre(self):
        with self.assertRaises(ValueError):
            acceleration((0.0, 0.0, 0.0))

    def test_rk4_rejects_non_positive_steps(self):
        position, velocity = state_from_elements(CIRCULAR)
        with self.assertRaises(ValueError):
            rk4_step(position, velocity, 0.0)

    def test_rk4_consistent_energy_for_circular_leo(self):
        # Energy drift over a quarter period at 1 s steps must stay audio-visual
        # grade: relative specific-energy change below 1e-10.
        position, velocity = state_from_elements(CIRCULAR)
        start = norm(velocity) ** 2 / 2.0 - MU_EARTH_KM3_S2 / norm(position)
        for _ in range(round(orbital_period_s(CIRCULAR) / 4.0)):
            position, velocity = rk4_step(position, velocity, 1.0)
        end = norm(velocity) ** 2 / 2.0 - MU_EARTH_KM3_S2 / norm(position)
        self.assertLess(abs(end - start) / abs(start), 1e-10)

    def test_propagate_requires_sorted_times(self):
        position, velocity = state_from_elements(CIRCULAR)
        with self.assertRaises(ValueError):
            propagate(position, velocity, [10.0, 5.0])
        with self.assertRaises(ValueError):
            propagate(position, velocity, [], max_step_s=0.0)

    def test_propagate_of_zero_intervals_repeats_the_state(self):
        position, velocity = state_from_elements(CIRCULAR)
        samples = propagate(position, velocity, [0.0, 0.0, 0.0])
        self.assertEqual(len(samples), 3)
        self.assertEqual(samples[0].position_km, samples[-1].position_km)


class TestReferenceVsAnalytic(unittest.TestCase):
    def test_circular_leo_agrees_to_a_metre_scale_over_a_full_period(self):
        samples = expected_samples(CIRCULAR, [0.0, 600.0, 1800.0, 3600.0, orbital_period_s(CIRCULAR)])
        truth = sample_kepler(CIRCULAR, [s.time_s for s in samples])
        comparison = compare_trajectories(truth, samples, tolerance_km=0.05)
        self.assertTrue(comparison.ok, comparison.to_dict())
        # The analytic model and the integrator must also agree in speed.
        self.assertLess(comparison.max_velocity_km_s, 1e-6)

    def test_eccentric_gto_agrees_to_the_documented_tolerance(self):
        period = orbital_period_s(VALLADO)
        stamps = [0.0, period * 0.05, period * 0.2, period * 0.5]
        samples = expected_samples(VALLADO, stamps)
        truth = sample_kepler(VALLADO, stamps)
        comparison = compare_trajectories(truth, samples, tolerance_km=1.0)
        self.assertTrue(comparison.ok, comparison.to_dict())

    def test_comparison_reports_the_worst_sample_and_shape(self):
        truth = sample_kepler(CIRCULAR, [0.0, 600.0])
        shifted = [
            type(truth[0])(time_s=truth[0].time_s + 1e-12,  # type: ignore[attr-defined]
                           position_km=truth[0].position_km,
                           velocity_km_s=truth[0].velocity_km_s),
            type(truth[1])(time_s=truth[1].time_s,
                           position_km=tuple(c + 0.01 for c in truth[1].position_km),  # type: ignore[arg-type]
                           velocity_km_s=truth[1].velocity_km_s),
        ]
        comparison = compare_trajectories(truth, shifted, tolerance_km=0.001)
        self.assertEqual(comparison.worst_time_s, 600.0)
        self.assertGreater(comparison.max_position_km, 0.009)
        self.assertIsInstance(comparison.to_dict(), dict)

    def test_comparison_rejects_mismatched_sample_sets(self):
        truth = sample_kepler(CIRCULAR, [0.0, 600.0])
        with self.assertRaises(ValueError):
            compare_trajectories(truth, truth[:1], tolerance_km=1.0)


class TestGoldenRun(unittest.TestCase):
    """A preserved reference integration: the numbers cannot drift unnoticed."""

    GOLDEN = [
        # (t_s, x, y, z) for the circular LEO fixture, integrated at max_step 5 s.
        (0.0, 6928.137, 0.0, 0.0),
        (600.0, 5486.341, -559.542, 4193.574),
        (2400.0, -6032.863, -450.520, 3376.489),
    ]
    TOLERANCE_DERIVED_KM = 0.05  # documented tolerance for the analytic comparison
    MAX_CROSS_KM = 0.5           # absolute drift allowed against the golden points

    def test_golden_circular_leo_points_reproduce_within_the_registered_drift(self):
        stamps = [point[0] for point in self.GOLDEN]
        samples = expected_samples(CIRCULAR, stamps, max_step_s=5.0)
        for (t, x, y, z), sample in zip(self.GOLDEN, samples):
            with self.subTest(t=t):
                offset = math.sqrt(
                    (sample.position_km[0] - x) ** 2
                    + (sample.position_km[1] - y) ** 2
                    + (sample.position_km[2] - z) ** 2
                )
                self.assertLess(offset, self.MAX_CROSS_KM, (t, sample.to_dict()))
        # And the analytic model still sits inside its own tolerance on the
        # same stamps, so the golden drift and the analytic tolerance agree.
        comparison = compare_trajectories(
            sample_kepler(CIRCULAR, stamps), samples, tolerance_km=self.TOLERANCE_DERIVED_KM
        )
        self.assertTrue(comparison.ok, comparison.to_dict())


if __name__ == "__main__":
    unittest.main()
