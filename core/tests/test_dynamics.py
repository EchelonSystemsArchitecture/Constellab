"""Day 15: registered Keplerian dynamics, reference vectors and circular fixture."""

from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from constellab_core.config import ConfigError, load_config, walker_delta_payload  # noqa: E402
from constellab_core.contract import OrbitElements, SCHEMA_VERSION  # noqa: E402
from constellab_core.dynamics import (  # noqa: E402
    DEFAULT_MODEL_KEY,
    dynamics_model,
    register_model,
    registered_models,
    unregister_model,
)
from constellab_core.orbit import (  # noqa: E402
    MU_EARTH_KM3_S2,
    orbital_period_s,
    snapshot_at_time,
    state_from_elements,
    state_from_elements_at_time,
)

# Vallado, "Fundamentals of Astrodynamics and Applications", Example 2-5:
# the inertial state vector that the published classical elements describe.
VALLADO_R_KM = (6524.834, 6862.875, 6448.296)
VALLADO_V_KM_S = (4.901327, 5.533756, -1.976341)
VALLADO_ELEMENTS = OrbitElements(
    semi_major_axis_km=36127.343,
    eccentricity=0.832853,
    inclination_deg=87.870,
    raan_deg=227.898,
    argument_of_perigee_deg=53.38,
    true_anomaly_deg=92.335,
)

# Circular LEO fixture: the special case the two-body model must handle with the
# same code path as any eccentric orbit (no separate circular propagator).
CIRCULAR = OrbitElements(
    semi_major_axis_km=6928.137,
    eccentricity=0.0,
    inclination_deg=97.6,
    raan_deg=0.0,
    argument_of_perigee_deg=0.0,
    true_anomaly_deg=0.0,
)


def _norm(v):
    return math.sqrt(sum(component * component for component in v))


def _sub(a, b):
    return tuple(x - y for x, y in zip(a, b))


def _cross(a, b):
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


class KeplerianStub:
    """A deliberately different propagator used to prove selection by key."""

    key = "test-shifted"
    label = "Test shifted propagator"
    assumptions = ("test only",)

    def state_at(self, elements, time_s):
        position, velocity = state_from_elements_at_time(elements, time_s)
        return (position[0] + 1.0, position[1], position[2]), velocity

    def period_s(self, elements):
        return orbital_period_s(elements)


class TestRegistry(unittest.TestCase):
    def test_default_model_is_registered_and_described(self):
        self.assertIn(DEFAULT_MODEL_KEY, registered_models())
        model = dynamics_model()
        self.assertEqual(model.key, DEFAULT_MODEL_KEY)
        self.assertIs(dynamics_model(DEFAULT_MODEL_KEY), model)
        # The limitations are data the UI can show, not prose in a docstring.
        self.assertTrue(any("no perturbations" in line for line in model.assumptions))

    def test_unknown_model_is_rejected_with_a_field_path(self):
        payload = walker_delta_payload(12, planes=3)
        payload["dynamics_model"] = "n-body-ephemeris"
        with self.assertRaises(ConfigError) as ctx:
            load_config(payload)
        self.assertEqual([e["path"] for e in ctx.exception.errors], ["$.dynamics_model"])
        self.assertIn("keplerian-two-body", ctx.exception.errors[0]["message"])

    def test_snapshot_generation_goes_through_the_registry(self):
        """Prove the loop selects the registered component instead of hard-coding it."""
        payload = walker_delta_payload(4, planes=2)
        kepler_snapshot = snapshot_at_time(load_config(payload), 60.0)
        before = kepler_snapshot.satellites[0].position_eci_km

        register_model(KeplerianStub())
        try:
            shifted = snapshot_at_time(
                load_config({**payload, "dynamics_model": "test-shifted"}), 60.0
            )
        finally:
            unregister_model("test-shifted")
        self.assertNotEqual(shifted.satellites[0].position_eci_km, before)
        self.assertAlmostEqual(shifted.satellites[0].position_eci_km[0], before[0] + 1.0, places=6)
        # And the default model still reproduces the Kepler state exactly.
        self.assertEqual(snapshot_at_time(load_config(payload), 60.0).satellites[0].position_eci_km, before)


class TestReferenceVectors(unittest.TestCase):
    def test_vallado_example_2_5_state_vector(self):
        """Published elements propagate to the published inertial state vector."""
        position, velocity = state_from_elements(VALLADO_ELEMENTS)
        self.assertLess(_norm(_sub(position, VALLADO_R_KM)), 2.0)
        self.assertLess(_norm(_sub(velocity, VALLADO_V_KM_S)), 0.002)
        # r x v is the orbit normal; its magnitude must equal sqrt(mu p) for the
        # published ellipse, p = a(1 - e^2).
        p = VALLADO_ELEMENTS.semi_major_axis_km * (1 - VALLADO_ELEMENTS.eccentricity ** 2)
        self.assertAlmostEqual(_norm(_cross(position, velocity)), math.sqrt(MU_EARTH_KM3_S2 * p), places=3)

    def test_eccentric_orbit_keeps_energy_and_angular_momentum(self):
        period = orbital_period_s(VALLADO_ELEMENTS)
        energy = -MU_EARTH_KM3_S2 / (2 * VALLADO_ELEMENTS.semi_major_axis_km)
        perigee = VALLADO_ELEMENTS.semi_major_axis_km * (1 - VALLADO_ELEMENTS.eccentricity)
        apogee = VALLADO_ELEMENTS.semi_major_axis_km * (1 + VALLADO_ELEMENTS.eccentricity)
        reference_h = _cross(*state_from_elements_at_time(VALLADO_ELEMENTS, 0.0))
        for fraction in (0.0, 0.125, 0.5, 0.75, 0.999):
            with self.subTest(fraction=fraction):
                position, velocity = state_from_elements_at_time(VALLADO_ELEMENTS, period * fraction)
                radius = _norm(position)
                speed_sq = sum(v * v for v in velocity)
                self.assertAlmostEqual(speed_sq / 2 - MU_EARTH_KM3_S2 / radius, energy, places=6)
                self.assertGreaterEqual(radius, perigee - 1e-6)
                self.assertLessEqual(radius, apogee + 1e-6)
                for expected, actual in zip(reference_h, _cross(position, velocity)):
                    self.assertAlmostEqual(expected, actual, places=6)


class TestCircularFixture(unittest.TestCase):
    def test_circular_orbit_has_constant_radius_and_speed(self):
        expected_radius = CIRCULAR.semi_major_axis_km
        expected_speed = math.sqrt(MU_EARTH_KM3_S2 / expected_radius)
        period = orbital_period_s(CIRCULAR)
        for fraction in (0.0, 0.1, 0.25, 0.5, 0.75, 0.9):
            with self.subTest(fraction=fraction):
                position, velocity = state_from_elements_at_time(CIRCULAR, period * fraction)
                self.assertAlmostEqual(_norm(position), expected_radius, places=6)
                self.assertAlmostEqual(_norm(velocity), expected_speed, places=9)

    def test_circular_orbit_stays_in_one_plane(self):
        # Derive the plane from the state itself: every later position must be
        # perpendicular to the epoch angular momentum, which must not rotate.
        epoch = state_from_elements_at_time(CIRCULAR, 0.0)
        normal = _cross(*epoch)
        normal_len = _norm(normal)
        normal = tuple(component / normal_len for component in normal)
        for time_s in (0.0, 600.0, 3600.0, 7200.0):
            with self.subTest(time_s=time_s):
                position, velocity = state_from_elements_at_time(CIRCULAR, time_s)
                self.assertAlmostEqual(sum(p * n for p, n in zip(position, normal)), 0.0, places=6)
                current = _cross(position, velocity)
                current_len = _norm(current)
                for expected, actual in zip(normal, current):
                    self.assertAlmostEqual(expected, actual / current_len, places=9)

    def test_period_returns_to_the_same_state_for_circular_and_eccentric(self):
        for elements in (CIRCULAR, VALLADO_ELEMENTS):
            with self.subTest(e=elements.eccentricity):
                start = state_from_elements_at_time(elements, 0.0)
                after = state_from_elements_at_time(elements, orbital_period_s(elements))
                for expected, actual in zip(start[0] + start[1], after[0] + after[1]):
                    self.assertAlmostEqual(expected, actual, places=5)


class TestGeneratedFleetUsesTheModel(unittest.TestCase):
    def test_walker_snapshots_keep_every_satellite_on_its_own_circle(self):
        config = load_config(walker_delta_payload(100, planes=10))
        snapshot = snapshot_at_time(config, 1500.0)
        radius = config.satellites[0].orbit.semi_major_axis_km
        self.assertEqual(len(snapshot.satellites), 100)
        for sat in snapshot.satellites:
            self.assertAlmostEqual(_norm(sat.position_eci_km), radius, places=3)

    def test_snapshot_reports_the_contract_version(self):
        config = load_config(walker_delta_payload(10, planes=2))
        self.assertEqual(snapshot_at_time(config, 0.0).schema_version, SCHEMA_VERSION)


if __name__ == "__main__":
    unittest.main()
