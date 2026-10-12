"""Day 2 contract tests: schema validity, round-trips, fixtures and the HTTP bridge."""

from __future__ import annotations

import dataclasses
import http.client
import json
import math
import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from constellab_core import SCHEMA_VERSION, __version__  # noqa: E402
from constellab_core.config import BUILTIN_SCENARIOS, builtin_scenario, load_config  # noqa: E402
from constellab_core.contract import (  # noqa: E402
    DEFINITIONS,
    SCHEMA,
    ContractError,
    SimulationConfig,
    SimulationSnapshot,
    is_compatible_version,
)
from constellab_core.orbit import EARTH_RADIUS_KM, MU_EARTH_KM3_S2, initial_snapshot, state_from_elements  # noqa: E402
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
            raw = _load(path)
            config = load_config(raw)
            self.assertEqual(config.scenario_id, name)
            self.assertEqual(SimulationConfig.from_dict(config.to_dict()), config)
            self.assertEqual(SimulationConfig.from_json(config.to_json()), config)
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
