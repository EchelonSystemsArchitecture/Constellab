"""Day 8 scenario loading: catalog, validated runtime load and field-path errors."""

from __future__ import annotations

import http.client
import json
import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from constellab_core.config import (  # noqa: E402
    BUILTIN_SCENARIOS,
    FLEET_PLANES,
    builtin_scenario,
    scenario_catalog,
    walker_delta_payload,
)
from constellab_core.service import CoreHandler, serve  # noqa: E402


class TestScenarioCatalog(unittest.TestCase):
    def test_catalog_is_derived_from_validated_configs(self):
        catalog = scenario_catalog()
        keys = {entry["key"] for entry in catalog}
        self.assertEqual(keys, set(BUILTIN_SCENARIOS))
        by_key = {entry["key"]: entry for entry in catalog}
        self.assertEqual(by_key["visual-orbit-demo"]["satellites"], 4)
        self.assertEqual(by_key["empty"]["satellites"], 0)
        self.assertEqual(by_key["swarm-48"]["satellites"], 48)
        self.assertEqual(by_key["swarm-48"]["scenario_id"], "swarm-48")

    def test_large_scenario_is_valid_and_unique(self):
        config = builtin_scenario("swarm-48")
        self.assertEqual(len(config.satellites), 48)
        self.assertEqual(len({s.id for s in config.satellites}), 48)
        for sat in config.satellites:
            self.assertGreater(sat.orbit.semi_major_axis_km, 6378.137)

    def test_generated_fleet_scenarios_have_the_requested_size(self):
        for key, count in (("swarm-100", 100), ("swarm-500", 500), ("swarm-1000", 1000)):
            with self.subTest(key=key):
                config = builtin_scenario(key)
                self.assertEqual(config.scenario_id, key)
                self.assertEqual(len(config.satellites), count)
                # Stable, unique ids: array order is never identity.
                self.assertEqual(len({s.id for s in config.satellites}), count)
                # Walker-delta shell: fixed planes, one satellite per anomaly slot.
                self.assertEqual(
                    len({round(s.orbit.raan_deg, 6) for s in config.satellites}),
                    FLEET_PLANES[key],
                )
                self.assertEqual(len({round(s.orbit.true_anomaly_deg, 6) for s in config.satellites}), count)
                self.assertEqual(config.dynamics_model, "keplerian-two-body")

    def test_generated_scenarios_are_deterministic_config_only(self):
        first = walker_delta_payload(100, planes=10)
        second = walker_delta_payload(100, planes=10)
        self.assertEqual(first, second)
        # The payload is data: no expression language, no seeded randomness that
        # would make a rerun on the same core produce a different fleet.
        satellites = first["satellites"]
        self.assertEqual(len({sat["id"] for sat in satellites}), 100)
        self.assertTrue(all(isinstance(sat["orbit"]["raan_deg"], float) for sat in satellites))


class TestScenarioApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._log = CoreHandler.log_message
        CoreHandler.log_message = lambda *a, **k: None
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

    def _reset(self):
        res, _ = self._request("POST", "/api/scenario", json.dumps({"key": "visual-orbit-demo"}))
        self.assertEqual(res.status, 200)

    def test_catalog_endpoint(self):
        res, payload = self._request("GET", "/api/scenarios")
        self.assertEqual(res.status, 200)
        self.assertIn("swarm-48", {s["key"] for s in payload["scenarios"]})
        self.assertIn("active", payload)

    def test_load_by_key_restarts_the_clock(self):
        self._reset()
        # Park the running clock far ahead so an inherited time would be obvious.
        self._request("POST", "/api/clock/pause", json.dumps({}))
        self._request("POST", "/api/clock/time_scale", json.dumps({"time_scale": 1}))
        for _ in range(100):
            self._request("POST", "/api/clock/step", json.dumps({}))
        res, before = self._request("GET", "/api/snapshot")
        self.assertEqual(res.status, 200)
        self.assertGreater(before["clock"]["simulation_time_s"], 90)

        res, payload = self._request("POST", "/api/scenario", json.dumps({"key": "swarm-48"}))
        self.assertEqual(res.status, 200)
        self.assertEqual(payload["scenario"]["scenario_id"], "swarm-48")
        self.assertEqual(len(payload["scenario"]["satellites"]), 48)
        self.assertEqual(payload["clock"]["paused"], False)
        self.assertEqual(payload["clock"]["simulation_time_s"], 0.0)

        res, snap = self._request("GET", "/api/snapshot")
        self.assertEqual(res.status, 200)
        self.assertEqual(snap["scenario_id"], "swarm-48")
        self.assertEqual(len(snap["satellites"]), 48)
        # Loading restarts the clock: the new scenario does not inherit old time.
        # Generous bound: at the scenario's 60x scale this is well under a second
        # of wall time, so a slow machine can not make a restart look like a keep.
        self.assertLess(snap["clock"]["simulation_time_s"], 50.0)
        self._reset()

    def test_load_thousand_satellite_scenario(self):
        res, payload = self._request("POST", "/api/scenario", json.dumps({"key": "swarm-1000"}))
        self.assertEqual(res.status, 200)
        self.assertEqual(len(payload["scenario"]["satellites"]), 1000)
        res, snap = self._request("GET", "/api/state")
        self.assertEqual(res.status, 200)
        self.assertEqual(len(snap["snapshot"]["satellites"]), 1000)
        self.assertEqual(len({s["id"] for s in snap["snapshot"]["satellites"]}), 1000)
        self._reset()

    def test_unknown_key_is_a_structured_404(self):
        res, payload = self._request("POST", "/api/scenario", json.dumps({"key": "no-such-scenario"}))
        self.assertEqual(res.status, 404)
        self.assertEqual(payload["error"], "unknown_scenario")
        self.assertIn("swarm-48", payload["available"])

    def test_inline_config_adds_and_removes_satellites(self):
        base = builtin_scenario("visual-orbit-demo").to_dict()

        two = json.loads(json.dumps(base))
        two["scenario_id"] = "two-satellites"
        two["satellites"] = two["satellites"][:2]
        res, payload = self._request("POST", "/api/scenario", json.dumps({"config": two}))
        self.assertEqual(res.status, 200)
        self.assertEqual(len(payload["scenario"]["satellites"]), 2)
        self.assertNotIn("sat-charlie", {s["id"] for s in payload["scenario"]["satellites"]})

        res, snap = self._request("GET", "/api/snapshot")
        self.assertEqual(len(snap["satellites"]), 2)
        self._reset()

    def test_invalid_config_reports_the_exact_field_path(self):
        base = builtin_scenario("visual-orbit-demo").to_dict()

        duplicate = json.loads(json.dumps(base))
        duplicate["satellites"][1]["id"] = duplicate["satellites"][0]["id"]
        res, payload = self._request("POST", "/api/scenario", json.dumps({"config": duplicate}))
        self.assertEqual(res.status, 422)
        self.assertEqual(payload["errors"][0]["path"], "$.satellites[1].id")
        self.assertIn("duplicate", payload["errors"][0]["message"])

        bad_orbit = json.loads(json.dumps(base))
        bad_orbit["satellites"][0]["orbit"]["eccentricity"] = 1.5
        res, payload = self._request("POST", "/api/scenario", json.dumps({"config": bad_orbit}))
        self.assertEqual(res.status, 422)
        self.assertEqual(payload["errors"][0]["path"], "$.satellites[0].orbit.eccentricity")

        # The failed load must leave the running scenario untouched.
        res, snap = self._request("GET", "/api/snapshot")
        self.assertEqual(snap["scenario_id"], "visual-orbit-demo")
        self._reset()

    def test_expression_strings_are_rejected_as_unknown_fields(self):
        base = builtin_scenario("visual-orbit-demo").to_dict()
        base["satellites"][0]["orbit"]["update"] = "system('rm -rf /')"
        res, payload = self._request("POST", "/api/scenario", json.dumps({"config": base}))
        self.assertEqual(res.status, 422)
        self.assertEqual(payload["errors"][0]["path"], "$.satellites[0].orbit.update")
        self.assertEqual(payload["errors"][0]["message"], "unknown field")

    def test_missing_key_is_a_structured_400(self):
        res, payload = self._request("POST", "/api/scenario", json.dumps({}))
        self.assertEqual(res.status, 400)
        self.assertEqual(payload["error"], "missing_scenario_key")


if __name__ == "__main__":
    unittest.main()
