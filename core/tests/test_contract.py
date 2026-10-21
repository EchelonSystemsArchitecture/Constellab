"""Day 2 contract tests: schema validity, round-trips, fixtures and the HTTP bridge."""

from __future__ import annotations

import dataclasses
import http.client
import json
import math
import sys
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from constellab_core import SCHEMA_VERSION, __version__  # noqa: E402
from constellab_core.config import BUILTIN_SCENARIOS, builtin_scenario, load_config  # noqa: E402
from constellab_core.contract import (  # noqa: E402
    DEFINITIONS,
    SCHEMA,
    ContractError,
    OrbitElements,
    SimulationConfig,
    SimulationSnapshot,
    is_compatible_version,
)
from constellab_core.orbit import (  # noqa: E402
    EARTH_AXIAL_TILT_DEG,
    EARTH_RADIUS_KM,
    MU_EARTH_KM3_S2,
    SECONDS_PER_EARTH_SIDEREAL_DAY,
    earth_rotation_angle_rad,
    initial_snapshot,
    mean_motion_rad_s,
    orbital_period_s,
    state_from_elements,
    state_from_elements_at_time,
    true_anomaly_at_time,
)
from constellab_core.service import CoreHandler, serve  # noqa: E402
from constellab_core.validation import SchemaValidator, UnsupportedSchema  # noqa: E402

FIXTURES = Path(__file__).with_name("fixtures")


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _paths(exc: ContractError) -> set[str]:
    return {e["path"] for e in exc.errors}


class TestSchemaDocument(unittest.TestCase):
    def test_every_definition_has_a_dataclass_with_matching_fields(self):
        for name, cls in DEFINITIONS.items():
            schema_fields = set(SCHEMA["$defs"][name]["properties"])
            model_fields = {f.name for f in dataclasses.fields(cls)}
            self.assertEqual(schema_fields, model_fields, name)
            required = set(SCHEMA["$defs"][name]["required"])
            self.assertTrue(required <= model_fields, name)

    def test_schema_version_is_semver_and_matches_id(self):
        self.assertRegex(SCHEMA_VERSION, r"^\d+\.\d+\.\d+$")
        self.assertTrue(SCHEMA["$id"].endswith(SCHEMA_VERSION))

    def test_unsupported_keyword_is_rejected_not_ignored(self):
        with self.assertRaises(UnsupportedSchema):
            SchemaValidator({"$defs": {"X": {"type": "object", "patternProperties": {}}}})

    def test_ui_annotations_are_declared_for_editable_fields(self):
        # Day 9: the editor derives labels, units and steps from x-ui. The schema
        # validator must accept the annotation key and the metadata must cover
        # every field the editor expects to render.
        annotations = SCHEMA.get("x-ui", {})
        self.assertIn("OrbitElements.semi_major_axis_km", annotations)
        self.assertEqual(annotations["OrbitElements.semi_major_axis_km"]["unit"], "km")
        self.assertIn("SimulationConfig.time_scale", annotations)
        self.assertTrue(annotations["SimulationConfig.scenario_id"]["readOnly"])
        # The annotation is the only x-ui key; other x-* keys stay unsupported.
        with self.assertRaises(UnsupportedSchema):
            SchemaValidator({"x-custom": {}})


class TestVersionCompatibility(unittest.TestCase):
    def test_rules(self):
        major, minor, _ = (int(p) for p in SCHEMA_VERSION.split("."))
        self.assertTrue(is_compatible_version(SCHEMA_VERSION))
        self.assertTrue(is_compatible_version(f"{major}.{minor}.99"))
        self.assertFalse(is_compatible_version(f"{major + 1}.0.0"))
        self.assertFalse(is_compatible_version(f"{major}.{minor + 1}.0"))
        self.assertFalse(is_compatible_version("1"))
        self.assertFalse(is_compatible_version(1))

    def test_incompatible_snapshot_is_rejected_before_field_checks(self):
        payload = initial_snapshot(builtin_scenario("empty")).to_dict()
        payload["schema_version"] = "2.0.0"
        with self.assertRaises(ContractError) as ctx:
            SimulationSnapshot.from_dict(payload)
        self.assertEqual([e["path"] for e in ctx.exception.errors], ["$.schema_version"])


class TestFixtures(unittest.TestCase):
    def test_builtin_scenarios_round_trip(self):
        for name, path in BUILTIN_SCENARIOS.items():
            # Generated large-fleet scenarios have no file on disk (Day 11).
            raw = _load(path) if path is not None else None
            config = builtin_scenario(name) if raw is None else load_config(raw)
            self.assertEqual(config.scenario_id, name)
            self.assertEqual(SimulationConfig.from_dict(config.to_dict()), config)
            self.assertEqual(SimulationConfig.from_json(config.to_json()), config)
            if raw is not None:
                # defaults are applied on the way in, so to_dict() is a superset of the file
                self.assertEqual({k: v for k, v in config.to_dict().items() if k in raw}, raw)

    def test_empty_scenario_snapshot(self):
        snapshot = initial_snapshot(builtin_scenario("empty"))
        self.assertEqual(snapshot.satellites, [])
        self.assertEqual(snapshot.clock.simulation_time_s, 0.0)
        self.assertTrue(snapshot.clock.paused)
        self.assertEqual(SimulationSnapshot.from_json(snapshot.to_json()), snapshot)

    def test_four_satellite_snapshot_round_trip_and_ids(self):
        config = builtin_scenario("visual-orbit-demo")
        snapshot = initial_snapshot(config)
        self.assertEqual([s.id for s in snapshot.satellites], [s.id for s in config.satellites])
        self.assertEqual(snapshot.producer.version, __version__)
        self.assertEqual(SimulationSnapshot.from_dict(json.loads(snapshot.to_json())), snapshot)
        self.assertEqual(initial_snapshot(config), snapshot, "snapshot generation must be deterministic")

    def test_malformed_configs_fixture(self):
        for case in _load(FIXTURES / "malformed_configs.json")["cases"]:
            with self.subTest(case=case["name"]):
                with self.assertRaises(ContractError) as ctx:
                    SimulationConfig.from_dict(case["config"])
                self.assertTrue(set(case["expect_paths"]) <= _paths(ctx.exception),
                                f"expected {case['expect_paths']}, got {ctx.exception.errors}")

    def test_malformed_snapshots_fixture(self):
        for case in _load(FIXTURES / "malformed_snapshots.json")["cases"]:
            with self.subTest(case=case["name"]):
                with self.assertRaises(ContractError) as ctx:
                    SimulationSnapshot.from_dict(case["snapshot"])
                self.assertTrue(set(case["expect_paths"]) <= _paths(ctx.exception),
                                f"expected {case['expect_paths']}, got {ctx.exception.errors}")

    def test_all_errors_are_reported_at_once(self):
        with self.assertRaises(ContractError) as ctx:
            SimulationConfig.from_dict({"schema_version": SCHEMA_VERSION, "scenario_id": "x", "seed": -1,
                                        "epoch_utc": "bad", "satellites": [], "extra": 1})
        self.assertEqual(_paths(ctx.exception), {"$.seed", "$.epoch_utc", "$.extra"})


class TestOrbitConversion(unittest.TestCase):
    def test_circular_equatorial_orbit(self):
        config = load_config({**_load(BUILTIN_SCENARIOS["empty"]), "satellites": [{"id": "a", "orbit": {
            "semi_major_axis_km": 7000, "eccentricity": 0, "inclination_deg": 0, "raan_deg": 0,
            "argument_of_perigee_deg": 0, "true_anomaly_deg": 90}}]})
        position, velocity = state_from_elements(config.satellites[0].orbit)
        self.assertAlmostEqual(position[0], 0.0, places=9)
        self.assertAlmostEqual(position[1], 7000.0, places=9)
        self.assertAlmostEqual(velocity[0], -math.sqrt(MU_EARTH_KM3_S2 / 7000), places=9)
        self.assertAlmostEqual(velocity[1], 0.0, places=9)

    def test_demo_satellites_are_above_earth_and_bound(self):
        for sat in initial_snapshot(builtin_scenario()).satellites:
            r = math.sqrt(sum(x * x for x in sat.position_eci_km))
            v2 = sum(x * x for x in sat.velocity_eci_km_s)
            self.assertGreater(r, EARTH_RADIUS_KM, sat.id)
            self.assertLess(v2 / 2 - MU_EARTH_KM3_S2 / r, 0, f"{sat.id} must be gravitationally bound")


class TestOrbitPropagation(unittest.TestCase):
    """Day 5: position is an analytic function of simulation time."""

    def setUp(self):
        self.config = builtin_scenario()

    def test_epoch_true_anomaly_matches_declared_elements(self):
        for sat in self.config.satellites:
            with self.subTest(sat=sat.id):
                self.assertAlmostEqual(
                    true_anomaly_at_time(sat.orbit, 0.0) % 360.0,
                    sat.orbit.true_anomaly_deg % 360.0,
                    places=9,
                )

    def test_state_at_epoch_equals_t0_propagation(self):
        for sat in self.config.satellites:
            with self.subTest(sat=sat.id):
                epoch = state_from_elements(sat.orbit)
                at_zero = state_from_elements_at_time(sat.orbit, 0.0)
                for expected, actual in zip(epoch[0] + epoch[1], at_zero[0] + at_zero[1]):
                    self.assertAlmostEqual(expected, actual, places=6, msg=sat.id)

    def test_one_full_period_returns_to_the_epoch_position(self):
        for sat in self.config.satellites:
            with self.subTest(sat=sat.id):
                start = state_from_elements(sat.orbit)[0]
                after = state_from_elements_at_time(sat.orbit, orbital_period_s(sat.orbit))[0]
                for axis, (a, b) in enumerate(zip(start, after)):
                    self.assertAlmostEqual(a, b, places=6, msg=f"{sat.id} axis {axis}")

    def test_propagated_radius_follows_the_element_ellipse(self):
        for sat in self.config.satellites:
            orbit = sat.orbit
            p = orbit.semi_major_axis_km * (1.0 - orbit.eccentricity ** 2)
            for elapsed in (0.0, 60.0, 600.0, 3600.0, 20000.0):
                position, _ = state_from_elements_at_time(orbit, elapsed)
                radius = math.sqrt(sum(v * v for v in position))
                nu = math.radians(true_anomaly_at_time(orbit, elapsed))
                expected = p / (1.0 + orbit.eccentricity * math.cos(nu))
                with self.subTest(sat=sat.id, t=elapsed):
                    self.assertAlmostEqual(radius, expected, places=6)

    def test_circular_orbit_advances_at_mean_motion(self):
        elements = OrbitElements(
            semi_major_axis_km=7000.0,
            eccentricity=0.0,
            inclination_deg=0.0,
            raan_deg=0.0,
            argument_of_perigee_deg=0.0,
            true_anomaly_deg=0.0,
        )
        elapsed = 120.0
        advanced = true_anomaly_at_time(elements, elapsed) - true_anomaly_at_time(elements, 0.0)
        self.assertAlmostEqual(advanced, math.degrees(mean_motion_rad_s(elements) * elapsed), places=6)

    def test_snapshot_uses_the_supplied_clock(self):
        from constellab_core.contract import SimulationClock
        from constellab_core.orbit import snapshot_at_time
        from constellab_core.service import running_clock

        clock = SimulationClock(epoch_utc="2026-10-12T00:00:00Z", simulation_time_s=0.0, time_scale=300.0, paused=False)
        snapshot = snapshot_at_time(self.config, 42.0, clock)
        self.assertFalse(snapshot.clock.paused)
        self.assertEqual(snapshot.clock.time_scale, 300.0)
        self.assertEqual(snapshot.clock.simulation_time_s, 42.0)
        self.assertFalse(running_clock(self.config).paused)

    def test_positions_change_over_time(self):
        sat = self.config.satellites[0]
        first = state_from_elements_at_time(sat.orbit, 0.0)[0]
        later = state_from_elements_at_time(sat.orbit, 600.0)[0]
        self.assertNotEqual(tuple(round(x, 6) for x in first), tuple(round(x, 6) for x in later))

    def test_earth_spin_is_not_applied_inside_the_inertial_frame(self):
        """ECI is fixed at epoch: only the orbit may move a satellite in it.

        A circular equatorial orbit is the sharpest check: its argument of
        latitude must advance by exactly mean-motion x time. Any hidden Earth
        spin (2.5° over 600 s) shows up immediately as a mismatch.
        """
        elements = OrbitElements(
            semi_major_axis_km=7000.0,
            eccentricity=0.0,
            inclination_deg=0.0,
            raan_deg=0.0,
            argument_of_perigee_deg=0.0,
            true_anomaly_deg=0.0,
        )
        elapsed = 600.0
        position, velocity = state_from_elements_at_time(elements, elapsed)
        latitude_longitude = math.degrees(math.atan2(position[1], position[0]))
        expected = math.degrees(mean_motion_rad_s(elements) * elapsed)
        self.assertAlmostEqual(latitude_longitude, expected, places=6)
        # Speed is unchanged by any rotation, so this pins the magnitude too.
        self.assertAlmostEqual(
            math.sqrt(sum(v * v for v in velocity)), math.sqrt(MU_EARTH_KM3_S2 / 7000.0), places=9
        )

    def test_earth_rotation_uses_the_real_sidereal_day(self):
        self.assertEqual(SECONDS_PER_EARTH_SIDEREAL_DAY, 86164.0905)
        self.assertEqual(EARTH_AXIAL_TILT_DEG, 23.44)
        # 360° per sidereal day = 15.041° per hour of simulated time.
        self.assertAlmostEqual(
            math.degrees(earth_rotation_angle_rad(3600.0)), 15.0411, places=3
        )
        self.assertAlmostEqual(earth_rotation_angle_rad(0.0), 0.0, places=12)
        # A full turn wraps to zero instead of growing without bound.
        self.assertAlmostEqual(
            earth_rotation_angle_rad(SECONDS_PER_EARTH_SIDEREAL_DAY * 3), 0.0, places=9
        )
        half = math.degrees(earth_rotation_angle_rad(SECONDS_PER_EARTH_SIDEREAL_DAY / 2))
        self.assertAlmostEqual(half, 180.0, places=9)


class TestHttpBridge(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._log = CoreHandler.log_message
        CoreHandler.log_message = lambda *a, **k: None  # keep test output clean
        cls.server = serve("127.0.0.1", 0)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.port = cls.server.server_address[1]

    @classmethod
    def tearDownClass(cls):
        CoreHandler.log_message = cls._log
        cls.server.shutdown()
        cls.server.server_close()

    def _request(self, method, path, body=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        headers = {"Content-Type": "application/json"} if body is not None else {}
        conn.request(method, path, body=body, headers=headers)
        res = conn.getresponse()
        data = res.read()
        conn.close()
        return res, json.loads(data) if data else None

    def test_cors_and_snapshot(self):
        res, payload = self._request("GET", "/api/snapshot")
        self.assertEqual(res.status, 200)
        self.assertEqual(res.getheader("Access-Control-Allow-Origin"), "*")
        snapshot = SimulationSnapshot.from_dict(payload)
        self.assertEqual(len(snapshot.satellites), 4)
        res, _ = self._request("OPTIONS", "/api/snapshot")
        self.assertEqual(res.status, 204)

    def test_service_clock_runs_and_advances(self):
        res, first = self._request("GET", "/api/snapshot")
        self.assertEqual(res.status, 200)
        self.assertFalse(first["clock"]["paused"])
        self.assertGreater(first["clock"]["time_scale"], 0)
        second = first
        for _ in range(20):
            time.sleep(0.1)
            _, second = self._request("GET", "/api/snapshot")
            if second["clock"]["simulation_time_s"] > first["clock"]["simulation_time_s"]:
                break
        self.assertGreater(second["clock"]["simulation_time_s"], first["clock"]["simulation_time_s"])

    def test_contract_endpoint_serves_the_schema(self):
        res, payload = self._request("GET", "/api/contract")
        self.assertEqual(res.status, 200)
        self.assertEqual(payload["x-schema-version"], SCHEMA_VERSION)

    def test_snapshot_for_posted_config(self):
        res, payload = self._request("POST", "/api/snapshot", BUILTIN_SCENARIOS["empty"].read_bytes())
        self.assertEqual(res.status, 200)
        self.assertEqual(payload["satellites"], [])
        res, payload = self._request("POST", "/api/snapshot", b'{"schema_version": "9.0.0"}')
        self.assertEqual(res.status, 422)
        self.assertEqual(payload["errors"][0]["path"], "$.schema_version")


if __name__ == "__main__":
    unittest.main()
