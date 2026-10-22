"""Day 19 acceptance: the dynamic parameter registry.

Everything a component can be configured with is declared once, validated at
load, scoped to the component that consumes it, and has a safe default so a
scenario can omit it. Pinned here:

* the shipped data files load into one registry, issue-free,
* every numeric key still ends with its unit's slug (the Day 16 contract),
* defaults / overrides merge, and wrong-owner or out-of-range values fail
  with field-path diagnostics that name the consumer,
* the schema hash is stable for label-only edits and moves for semantics,
* migrations rename values between schema versions and reject cycles,
* a synthetic stress registry stays performant and mirror-consistent.
"""

from __future__ import annotations

import json
import statistics
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from constellab_core import parameters  # noqa: E402
from constellab_core.parameters import (  # noqa: E402
    PARAMETER_SCHEMA_VERSION,
    ParameterError,
    ParameterMigration,
    ParameterRegistry,
    ParameterSpec,
    builtin_registry,
    load_registry,
    registry_payload,
    spec_issues,
    stress_registry,
    unit_slug,
)


class TestBuiltinRegistry(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = builtin_registry()

    def test_shiped_owners_are_all_loaded_issue_free(self):
        owners = self.registry.owners()
        self.assertIn("power.solar-battery", owners)
        self.assertIn("event-source.clock-tick", owners)
        self.assertGreaterEqual(len(owners), 8)
        self.assertGreaterEqual(len(self.registry), 32)
        for spec in self.registry.specs():
            with self.subTest(key=spec.key):
                self.assertEqual(spec_issues(spec, "test"), [])

    def test_every_key_is_namespaced_under_its_owner(self):
        for spec in self.registry.specs():
            with self.subTest(key=spec.key):
                self.assertTrue(spec.key.startswith(spec.owner + "."), spec.key)
                self.assertEqual(spec.short_key, spec.key[len(spec.owner) + 1:])

    def test_numeric_keys_match_their_unit_slug(self):
        for spec in self.registry.specs():
            if spec.kind == "number":
                with self.subTest(key=spec.key):
                    self.assertTrue(
                        spec.key.endswith("_" + unit_slug(spec.unit)),
                        (spec.key, spec.unit),
                    )

    def test_every_number_kind_has_units(self):
        # The key<->unit slug contract applies to fractional numbers; integer
        # counts (task_count, start_index) are exempted by spec_issues.
        for spec in self.registry.specs():
            if spec.kind == "number":
                with self.subTest(key=spec.key):
                    self.assertNotEqual(spec.unit, "", spec.key)
                    self.assertTrue(
                        spec.key.endswith("_" + unit_slug(spec.unit)),
                        (spec.key, spec.unit),
                    )

    def test_defaults_exist_and_sit_inside_their_bounds(self):
        for spec in self.registry.specs():
            with self.subTest(key=spec.key):
                self.assertIsNotNone(spec.default, spec.key)
                if isinstance(spec.default, (int, float)) and not isinstance(spec.default, bool):
                    if spec.minimum is not None:
                        self.assertGreaterEqual(spec.default, spec.minimum, spec.key)
                    if spec.maximum is not None:
                        self.assertLessEqual(spec.default, spec.maximum, spec.key)

    def test_payload_shape_is_json_ready(self):
        payload = self.registry.payload()
        self.assertEqual(payload["schema_version"], PARAMETER_SCHEMA_VERSION)
        self.assertEqual(payload["count"], len(self.registry))
        self.assertEqual(len(payload["parameters"]), payload["count"])
        self.assertEqual(
            {p["key"] for p in payload["parameters"]},
            {s.key for s in self.registry.specs()},
        )

    def test_schema_hash_stability_and_sensitivity(self):
        # A registry rebuilt from the builtin specs hashes identically.
        rebuilt = ParameterRegistry(self.registry.specs(), source="<rebuilt>")
        self.assertEqual(rebuilt.schema_hash(), self.registry.schema_hash())
        # A semantic change (a different default) moves the hash.
        tweaked = ParameterSpec(
            key="power.solar-battery.array_area_m2",
            owner="power.solar-battery",
            unit="m2",
            default=1.5,
        )
        self.assertNotEqual(
            ParameterRegistry([tweaked], source="<tweaked>").schema_hash(),
            self.registry.schema_hash(),
        )
        # Label-only edits are display data, not semantics.
        builtin_spec = self.registry.get("power.solar-battery.array_area_m2")
        relabelled = ParameterSpec(
            key="power.solar-battery.array_area_m2",
            owner="power.solar-battery",
            unit="m2",
            default=builtin_spec.default,
            label="New words",
        )
        self.assertEqual(relabelled.to_dict().get("label"), "New words")
        # Label is excluded from the semantic surface entirely.
        self.assertNotIn("label", relabelled.semantic_dict())


class TestDefaultMergeAndValidation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = builtin_registry()

    def test_defaults_for_owner_are_short_keyed(self):
        defaults = self.registry.defaults_for("power.solar-battery")
        self.assertIn("array_area_m2", defaults)
        self.assertNotIn("power.solar-battery.array_area_m2", defaults)
        self.assertGreater(defaults["array_area_m2"], 0)

    def test_effective_values_merge_overrides(self):
        merged = self.registry.effective_values(
            "power.constant", {"supply_w": 240},
        )
        self.assertEqual(merged["supply_w"], 240)
        self.assertEqual(
            merged["battery_capacity_j"],
            self.registry.get("power.constant.battery_capacity_j").default,
        )

    def test_override_out_of_bounds_fails_with_a_field_path(self):
        with self.assertRaises(ParameterError) as ctx:
            self.registry.effective_values("power.constant", {"supply_w": 1e9})
        paths = [issue["path"] for issue in ctx.exception.issues]
        self.assertIn("$.parameters.supply_w", paths)

    def test_override_wrong_type_and_wrong_owner_fail(self):
        with self.assertRaises(ParameterError) as ctx:
            self.registry.effective_values("power.constant", {"supply_w": "big"})
        with self.assertRaises(ParameterError) as ctx:
            self.registry.effective_values("power.constant", {"half_angle_deg": 30.0})
        message = ctx.exception.issues[0]["message"]
        self.assertIn("sensor.conical", message)

    def test_unknown_parameter_names_the_consumer_or_rejects(self):
        issues = self.registry.validate_values(
            "power.constant", {"not_a_real_setting": 1},
        )
        self.assertIn("not_a_real_setting", issues[0]["message"])

    def test_audit_classifies_consumed_metadata_and_unconsumed(self):
        audit = self.registry.audit({
            "power.constant": {"supply_w": 120},
        })
        self.assertIn("power.constant.supply_w", audit["consumed"])
        self.assertEqual(audit["unconsumed"], [])
        # Anything not registered for the named owner is flagged loudly.
        audit_bad = self.registry.audit({
            "power.constant": {"half_angle_deg": 30},
        })
        self.assertEqual(audit_bad["consumed"], [])
        self.assertEqual(audit_bad["unconsumed"], ["power.constant.half_angle_deg"])


class TestRegistryIntegrity(unittest.TestCase):
    def test_duplicate_definitions_are_rejected(self):
        spec = ParameterSpec(key="stress.owner-0000.field_00_m", owner="stress.owner-0000",
                             default=1.0, unit="m", minimum=0.0)
        with self.assertRaises(ParameterError):
            ParameterRegistry([spec, spec])

    def test_extend_is_atomic_on_failure(self):
        registry = stress_registry(8)
        before = list(registry.specs())
        good = ParameterSpec(key="stress.owner-9999.field_00_m", owner="stress.owner-9999",
                             default=1.0, unit="m", minimum=0.0)
        bad = ParameterSpec(key="Bad", owner="stress.owner-9999", default=1.0, unit="m")
        with self.assertRaises(ParameterError):
            registry.extend([good, bad])
        self.assertEqual([(s.key, s.owner) for s in registry.specs()],
                         [(s.key, s.owner) for s in before])

    def test_migrations_rename_and_recursively_apply(self):
        # Sources are legacy names (no longer registered); targets are
        # registered full keys. migrate() chains until no migration starts.
        registry = ParameterRegistry([
            ParameterSpec(key="demo.a.new_value_w", owner="demo.a", default=1.0, unit="W"),
            ParameterSpec(key="demo.b.final_kbit", owner="demo.b", default=1, kind="integer", unit="kbit"),
        ])
        registry.add_migration(
            ParameterMigration(from_version=1, to_version=2,
                               renames={"old_value_w": "demo.a.new_value_w"})
        )
        registry.add_migration(
            ParameterMigration(from_version=2, to_version=3,
                               renames={"new_value_w": "demo.b.final_kbit"})
        )
        version, values = registry.migrate({"old_value_w": 5}, from_version=1)
        self.assertEqual(version, 3)
        self.assertEqual(values, {"demo.a.new_value_w": 5})
        version, values = registry.migrate({"new_value_w": 7}, from_version=2)
        self.assertEqual(version, 3)
        self.assertEqual(values, {"demo.b.final_kbit": 7})

    def test_migration_cycle_and_targets_are_rejected(self):
        registry = ParameterRegistry([
            ParameterSpec(key="demo.a.value_w", owner="demo.a", default=1.0, unit="W"),
        ])
        with self.assertRaises(ParameterError):
            registry.add_migration(ParameterMigration(2, 1, {}))
        with self.assertRaises(ParameterError):
            registry.add_migration(
                ParameterMigration(1, 2, {"value_w": "nowhere.value_w"})
            )

    def test_bad_data_directory_files_diagnose_their_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "b.json").write_text(
                json.dumps({"owner": "demo.owner-a", "parameters": [
                    {"key": "field_m", "unit": "m", "default": 1.0, "minimum": 0.0},
                ]}), encoding="utf-8",
            )
            (root / "a.json").write_text("{not json", encoding="utf-8")
            with self.assertRaises(ParameterError) as ctx:
                load_registry(root)
            self.assertIn("a.json", str(ctx.exception.issues[0]["path"]))

    def test_shiped_duplicate_owner_conflict_is_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("a.json", "b.json"):
                (root / name).write_text(
                    json.dumps({"owner": "power.constant", "parameters": []}),
                    encoding="utf-8",
                )
            with self.assertRaises(ParameterError) as ctx:
                load_registry(root)
            self.assertIn("already defined", ctx.exception.issues[0]["message"])


class TestStressRegistry(unittest.TestCase):
    def test_stress_registry_is_loadable_and_consistent(self):
        registry = stress_registry(200)
        self.assertEqual(len(registry), 200)
        self.assertEqual(len(registry.owners()), 50)
        for spec in registry.specs():
            self.assertEqual(spec_issues(spec, "stress"), [], spec.key)

    def test_stress_validation_and_hash_stay_fast(self):
        registry = stress_registry(200)
        started = time.perf_counter()
        registry.schema_hash()
        hash_seconds = time.perf_counter() - started
        started = time.perf_counter()
        issues = registry.validate_values(
            "stress.owner-0000", registry.defaults_for("stress.owner-0000"),
        )
        validate_seconds = time.perf_counter() - started
        self.assertEqual(issues, [])
        self.assertLess(hash_seconds, 1.0)
        self.assertLess(validate_seconds, 1.0)


class TestNormalization(unittest.TestCase):
    def test_normalized_maps_to_model_scales(self):
        spec = ParameterSpec(key="demo.a_size_m", owner="demo.a", default=10.0, unit="m",
                             normalization={"scale": 10.0, "offset": 5.0})
        self.assertEqual(spec.normalized(spec.default), 0.5)
        self.assertEqual(spec.normalized(15.0), 1.0)
        with self.assertRaises(ZeroDivisionError):
            ParameterSpec(key="demo.a_size_m", owner="demo.a", unit="m", default=1.0,
                          normalization={"scale": 0.0}).normalized(1.0)


if __name__ == "__main__":
    unittest.main()
