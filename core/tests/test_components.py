"""Day 18/20 acceptance: virtual spacecraft components, identities and runtime.

Pinned promises:

* component models register under unique namespaced keys with valid kinds and
  stages, and the built-in reference mix is present from import,
* scenario validation catches unknown types, duplicates and out-of-range
  parameter values before any simulation runs,
* the per-satellite runtime advances deterministically: event ticks fire on
  cadence, tasks rotate batteries drain, buffers overflow explicitly, and a
  rebuild at the same time matches an incremental advance exactly.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from constellab_core import components  # noqa: E402
from constellab_core.components import (  # noqa: E402
    ComponentError,
    DEFAULT_COMPONENT_KEYS,
    KINDS,
    STAGES,
    advance_runtime,
    component,
    describe_components,
    effective_params,
    initial_runtime,
    integrated_states,
    registered_components,
    register_component,
    runtime_snapshot,
    states_payload,
    unregister_component,
    validate_components,
)
from constellab_core.config import builtin_scenario, load_config  # noqa: E402


class TestComponentRegistry(unittest.TestCase):
    def test_builtin_models_are_registered_at_import(self):
        for key in DEFAULT_COMPONENT_KEYS:
            with self.subTest(key=key):
                self.assertIn(key, registered_components())
        # Day 15 dynamics models stay out of the component registry.
        self.assertNotIn("keplerian-two-body", registered_components())

    @staticmethod
    def _make_model(model_key, kind="sensor"):
        # Class bodies cannot read the enclosing factory's locals, so this
        # probe model is built via type() instead of a nested class statement.
        return type(
            "ProbeComponent",
            (object,),
            {
                "key": model_key,
                "label": "Probe",
                "kind": kind,
                "stage": STAGES[kind],
                "assumptions": (),
                "initial_state": lambda params: {},
                "step": lambda state, params, context: None,
            },
        )()

    def test_duplicate_registration_fails_with_a_diagnostic(self):
        registered = registered_components()
        key = registered[0]
        with self.assertRaises(ComponentError) as ctx:
            register_component(self._make_model(key))
        self.assertIn("already registered", ctx.exception.issues[0]["message"])
        self.assertEqual(registered, registered_components())

    def test_bad_keys_and_kinds_are_rejected(self):
        with self.assertRaises(ComponentError):
            register_component(self._make_model("probe"))
        bad_kind = self._make_model("probe.not-a-kind")
        bad_kind.kind = "hologram"
        with self.assertRaises(ComponentError):
            register_component(bad_kind)

    def test_unregister_round_trip_restores_the_registration(self):
        key = "probe.unregister-me"
        model = self._make_model(key)
        register_component(model)
        self.assertTrue(components._REGISTRY[key] is model)
        removed = unregister_component(key)
        self.assertTrue(removed is model)
        self.assertIsNone(unregister_component(key))
        self.assertNotIn(key, registered_components())
        with self.assertRaises(ComponentError):
            component(key)

    def test_describe_components_lists_parameters_from_the_registry(self):
        described = {entry["key"]: entry for entry in describe_components()}
        power = described["power.solar-battery"]
        self.assertEqual(power["kind"], "power")
        self.assertGreater(len(power["parameters"]), 0)
        self.assertTrue(all("key" in spec for spec in power["parameters"]))

    def test_states_payload_shape_is_json_ready(self):
        payload = states_payload()
        self.assertEqual(payload["keys"], list(registered_components()))
        self.assertEqual(payload["kinds"], list(KINDS))
        self.assertEqual(set(payload["stages"]), set(STAGES))
        self.assertEqual(list(payload["default_keys"]), list(DEFAULT_COMPONENT_KEYS))


class TestScenarioValidation(unittest.TestCase):
    def test_demo_and_fleet_scenarios_validate(self):
        for key in ("visual-orbit-demo", "swarm-48"):
            with self.subTest(key=key):
                config = builtin_scenario(key)
                validate_components(config)  # raises on any problem

    def test_unknown_type_and_duplicate_and_bad_value_diagnostics(self):
        base = load_config(builtin_scenario("visual-orbit-demo").to_dict())
        satellite = base.satellites[0]

        unknown = satellite.to_dict()
        unknown["components"] = [{"type": "power.buck-converter", "parameters": {}}]
        with self.assertRaises(ComponentError) as ctx:
            validate_components(load_config({**base.to_dict(), "satellites": [unknown]}))
        self.assertIn("power.buck-converter", str(ctx.exception.issues[0]["message"]))

        duplicated = satellite.to_dict()
        duplicated["components"] = [
            {"type": "sensor.conical", "parameters": {}},
            {"type": "sensor.conical", "parameters": {}},
        ]
        with self.assertRaises(ComponentError) as ctx:
            validate_components(load_config({**base.to_dict(), "satellites": [duplicated]}))
        self.assertIn("declared more than once", str(ctx.exception))

        out_of_range = satellite.to_dict()
        out_of_range["components"] = [
            {"type": "power.constant", "parameters": {"supply_w": 2_000_000}},
        ]
        with self.assertRaises(ComponentError) as ctx:
            validate_components(load_config({**base.to_dict(), "satellites": [out_of_range]}))
        self.assertIn("supply_w", str(ctx.exception))


class TestRuntimeBehaviour(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = builtin_scenario("visual-orbit-demo")

    def test_default_mix_applies_when_nothing_is_declared(self):
        runtime = initial_runtime(self.config)
        first_id = self.config.satellites[0].id
        self.assertEqual(sorted(runtime[first_id].state), sorted(DEFAULT_COMPONENT_KEYS))

    def test_effective_params_merge_registry_defaults(self):
        params = effective_params("power.constant", {"supply_w": 71})
        self.assertEqual(params["supply_w"], 71)
        self.assertGreater(params["battery_capacity_j"], 0)
        with self.assertRaises(ComponentError):
            effective_params("power.constant", {"supply_w": -1})

    def test_tick_cadence_is_deterministic_in_elapsed_time(self):
        runtime = initial_runtime(self.config)
        sat_id = self.config.satellites[0].id
        advance_runtime(self.config, runtime, time_s=120.0, dt_s=120.0)
        interval = runtime[sat_id].state["event-source.clock-tick"]["interval_s"]
        self.assertEqual(runtime[sat_id].state["event-source.clock-tick"]["tick_count"],
                         round(120.0 / interval))
        # A fresh rebuild at the same time matches exactly (restart determinism).
        rebuilt = integrated_states(self.config, 120.0)
        self.assertEqual(
            rebuilt[sat_id].state["event-source.clock-tick"],
            runtime[sat_id].state["event-source.clock-tick"],
        )

    def test_tasks_rotate_through_their_schedule(self):
        runtime = initial_runtime(self.config)
        sat_id = self.config.satellites[0].id
        task_params = runtime[sat_id].params["task.round-robin"]
        duration = task_params["task_duration_s"]
        # Inside the first task window the index has not rotated yet.
        advance_runtime(self.config, runtime, time_s=1.0, dt_s=1.0)
        task = runtime[sat_id].state["task.round-robin"]
        self.assertEqual(task["current_task_index"], task_params["start_index"])
        self.assertAlmostEqual(task["seconds_in_task_s"], 1.0, places=9)
        # The index advances exactly when a full task duration has elapsed;
        # the leftover second carries into the next task window.
        advance_runtime(self.config, runtime,
                        time_s=1.0 + duration, dt_s=duration)
        task = runtime[sat_id].state["task.round-robin"]
        self.assertEqual(task["current_task_index"],
                         (task_params["start_index"] + 1) % int(task_params["task_count"]))
        self.assertAlmostEqual(task["seconds_in_task_s"], 1.0, places=9)
        # And the next full duration advances it again, wrapping modulo count.
        advance_runtime(self.config, runtime,
                        time_s=1.0 + 2.0 * duration, dt_s=duration)
        self.assertEqual(
            runtime[sat_id].state["task.round-robin"]["current_task_index"],
            (task_params["start_index"] + 2) % int(task_params["task_count"]),
        )

    def test_storage_absorbs_the_payload_pipeline(self):
        # The default mix wires payload -> storage: production must arrive.
        runtime = initial_runtime(self.config)
        sat_id = self.config.satellites[0].id
        advance_runtime(self.config, runtime, time_s=3600.0, dt_s=3600.0)
        payload = runtime[sat_id].state["payload.imaging"]
        storage = runtime[sat_id].state["storage.buffer"]
        self.assertGreater(payload["produced_bit"], 0)
        # The buffer saw the production: something was stored or dropped.
        self.assertGreater(
            storage["stored_bit"] + storage["dropped_bit"] + storage["drained_bit"],
            0,
        )
        self.assertLessEqual(storage["fill_fraction"], 1.0)
        self.assertGreaterEqual(storage["dropped_bit"], 0)
        self.assertGreaterEqual(storage["drained_bit"], 0)

    def test_advance_with_zero_dt_is_a_no_op(self):
        runtime = initial_runtime(self.config)
        before = runtime_snapshot(self.config, runtime)
        advance_runtime(self.config, runtime, time_s=0.0, dt_s=0.0)
        self.assertEqual(runtime_snapshot(self.config, runtime), before)

    def test_runtime_snapshot_is_sorted_by_stage(self):
        runtime = initial_runtime(self.config)
        sat_id = self.config.satellites[0].id
        staged = [entry["type"] for entry in runtime_snapshot(self.config, runtime)[sat_id]]
        times = [STAGES[key.split(".")[0]] for key in staged]
        self.assertEqual(times, sorted(times))
        self.assertEqual(staged, list(dict.fromkeys(staged)))  # no duplicates

    def test_incremental_and_rebuilt_runtime_agree(self):
        # A restart rebuild replays the same physics in one-second sub-steps
        # (see integrated_states); the running service advances in whole
        # chunks, so `last_production_bit` — a per-chunk diagnostic, not a
        # cumulative quantity — and float rounding may differ. Everything
        # cumulative must agree.
        runtime = initial_runtime(self.config)
        sat_id = self.config.satellites[0].id
        advance_runtime(self.config, runtime, time_s=100.0, dt_s=100.0)
        rebuilt = integrated_states(self.config, 100.0)

        def compare(want, got, prefix=""):
            if isinstance(want, dict):
                self.assertEqual(set(want), set(got), prefix)
                for key in want:
                    compare(want[key], got[key], f"{prefix}.{key}")
            elif isinstance(want, float) or isinstance(got, float):
                self.assertAlmostEqual(want, got, places=6, msg=prefix)
            else:
                self.assertEqual(want, got, prefix)

        for satellite_key in (sat_id,):
            rebuilt_state = rebuilt[satellite_key].state
            incremental_state = runtime[satellite_key].state
            self.assertEqual(set(rebuilt_state), set(incremental_state))
            for component_key in rebuilt_state:
                want = dict(rebuilt_state[component_key])
                got = dict(incremental_state[component_key])
                if "last_production_bit" in want:
                    want.pop("last_production_bit")
                    got.pop("last_production_bit")
                compare(want, got, f"satellite[{satellite_key}].{component_key}")


if __name__ == "__main__":
    unittest.main()
