"""Day 21 acceptance: declarative parameter constraints and dependencies."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from constellab_core.constraints import (  # noqa: E402
    ConstraintError,
    ConstraintRegistry,
    OneOfRule,
    Operand,
    RangeRule,
    RelationRule,
    RequiredIfRule,
    RequiresRule,
    SumBudgetRule,
    builtin_rules,
    check_parameters,
)
from constellab_core.parameters import (  # noqa: E402
    ParameterSpec,
    ParameterRegistry,
    builtin_registry,
)
from constellab_core.units import unit_kind  # noqa: E402


def make_registry(*pairs: tuple[str, str, float]) -> ParameterRegistry:
    specs = [ParameterSpec(key=key, owner=key.rsplit(".", 1)[0], default=default,
                           unit=unit, minimum=0.0 if unit != "1" else None)
             for key, unit, default in pairs]
    return ParameterRegistry(specs)


class TestDefinitionValidation(unittest.TestCase):
    def test_a_rule_must_reference_registered_parameters(self):
        registry = make_registry(("power.constant.supply_w", "W", 120.0))
        with self.assertRaises(ConstraintError) as caught:
            ConstraintRegistry([
                RelationRule(id="r1", kind="relation",
                             left=Operand(field="power.constant.nope_w"),
                             operator="<=", right=Operand.literal(1.0)),
            ], registry=registry)
        self.assertIn("power.constant.nope_w", str(caught.exception))

    def test_relations_across_unit_kinds_are_rejected(self):
        registry = make_registry(("power.constant.supply_w", "W", 120.0),
                                 ("sensor.device.breaker_m", "m", 1.0))
        with self.assertRaises(ConstraintError) as caught:
            ConstraintRegistry([
                RelationRule(id="r1", kind="relation",
                             left=Operand(field="power.constant.supply_w"),
                             operator="<=",
                             right=Operand(field="sensor.device.breaker_m")),
            ], registry=registry)
        self.assertIn("different quantity kinds", str(caught.exception))

    def test_sum_budget_across_unit_kinds_is_rejected(self):
        registry = make_registry(("power.constant.supply_w", "W", 120.0),
                                 ("sensor.device.breaker_m", "m", 1.0))
        with self.assertRaises(ConstraintError):
            ConstraintRegistry([
                SumBudgetRule(id="s", kind="sum-budget",
                              fields=("power.constant.supply_w", "sensor.breaker_m"),
                              maximum=10.0),
            ], registry=registry)

    def test_bad_operators_categories_and_duplicate_ids_fail(self):
        registry = make_registry(("power.constant.supply_w", "W", 120.0))
        with self.assertRaises(ConstraintError):
            ConstraintRegistry([RelationRule(
                id="r", kind="relation", left=Operand(field="power.constant.supply_w"),
                operator="<~", right=Operand.literal(1.0))], registry=registry)
        with self.assertRaises(ConstraintError):
            ConstraintRegistry([RelationRule(
                id="r", kind="relation", category="staging",
                left=Operand(field="power.constant.supply_w"),
                operator="<=", right=Operand.literal(1.0))], registry=registry)
        with self.assertRaises(ConstraintError) as caught:
            ConstraintRegistry([
                RangeRule(id="x", kind="range", field="power.constant.supply_w", minimum=0.0),
                RangeRule(id="x", kind="range", field="power.constant.supply_w", maximum=1.0),
            ], registry=registry)
        self.assertIn("duplicate rule id", str(caught.exception))

    def test_an_impossible_required_if_condition_is_rejected(self):
        options = (0, 1)
        registry = ParameterRegistry([
            ParameterSpec(key="power.constant.mode_ratio", owner="power.constant",
                          kind="number", unit="1", default=0, enum=options),
            ParameterSpec(key="power.constant.supply_w", owner="power.constant",
                          kind="number", unit="W", default=120.0, minimum=0.0),
        ])
        allowed = list(options)
        bad_value = allowed[0] + 97 if isinstance(allowed[0], (int, float)) else "not-a-mode"
        with self.assertRaises(ConstraintError) as caught:
            ConstraintRegistry([
                RequiredIfRule(id="ri", kind="required-if",
                               field="power.constant.supply_w",
                               condition_field="power.constant.mode_ratio",
                               equals=bad_value),
            ], registry=registry)
        self.assertIn("can never equal", str(caught.exception))


class TestDependencyGraph(unittest.TestCase):
    def test_requires_and_required_if_form_the_dependency_graph(self):
        registry = make_registry(("a.one.x_m", "m", 1.0), ("a.one.y_m", "m", 2.0),
                                 ("a.two.z_m", "m", 3.0))
        rules = ConstraintRegistry([
            RequiresRule(id="d1", kind="requires", field="a.one.x_m",
                         requires_field="a.one.y_m"),
            RequiredIfRule(id="d2", kind="required-if", field="a.two.z_m",
                           condition_field="a.one.x_m", equals=1.0),
        ], registry=registry)
        graph = rules.dependencies()
        self.assertEqual(graph["a.one.x_m"], {"a.one.y_m"})
        self.assertEqual(graph["a.two.z_m"], {"a.one.x_m"})
        self.assertNotIn("a.one.y_m", graph)
        self.assertEqual(rules.dependency_cycles(), [])

    def test_a_requires_cycle_is_rejected_before_startup(self):
        registry = make_registry(("a.one.x_m", "m", 1.0), ("a.one.y_m", "m", 2.0))
        with self.assertRaises(ConstraintError) as caught:
            rules = ConstraintRegistry([
                RequiresRule(id="c1", kind="requires", field="a.one.x_m",
                             requires_field="a.one.y_m"),
                RequiresRule(id="c2", kind="requires", field="a.one.y_m",
                             requires_field="a.one.x_m"),
            ], registry=registry)
            rules.check_graph()
        self.assertIn("dependency cycle", str(caught.exception))

    def test_self_requirement_is_rejected_at_definition_time(self):
        registry = make_registry(("a.one.x_m", "m", 1.0))
        with self.assertRaises(ConstraintError):
            ConstraintRegistry([
                RequiresRule(id="c", kind="requires", field="a.one.x_m",
                             requires_field="a.one.x_m"),
            ], registry=registry)


class TestEvaluation(unittest.TestCase):
    def setUp(self):
        self.registry = make_registry(
            ("power.constant.supply_w", "W", 120.0),
            ("power.constant.base_load_w", "W", 10.0),
            ("power.solar-battery.array_area_m2", "m2", 2.0),
            ("compute.capacity.duty_cycle_ratio", "1", 0.5),
            ("sensor.conical.duty_cycle_ratio", "1", 0.2),
            ("sensor.conical.half_angle_deg", "deg", 30.0),
        )
        self.rules = ConstraintRegistry([
            RelationRule(id="load", kind="relation",
                         left=Operand(field="power.constant.base_load_w"),
                         operator="<=",
                         right=Operand(field="power.constant.supply_w")),
            SumBudgetRule(id="duty", kind="sum-budget",
                          fields=("compute.capacity.duty_cycle_ratio",
                                  "sensor.conical.duty_cycle_ratio"),
                          maximum=1.0),
            RequiresRule(id="cfg", kind="requires",
                         field="power.constant.base_load_w",
                         requires_field="power.constant.supply_w"),
            RequiredIfRule(id="cond", kind="required-if",
                           field="power.constant.supply_w",
                           condition_field="sensor.conical.half_angle_deg",
                           condition_is_set=True),
            OneOfRule(id="one", kind="one-of",
                      fields=("power.constant.supply_w",
                              "power.solar-battery.array_area_m2"),
                      exactly=1),
            RangeRule(id="half", kind="range",
                      field="sensor.conical.half_angle_deg",
                      maximum=90.0),
        ], registry=self.registry)

    def test_clean_values_pass(self):
        self.assertEqual(self.rules.check({
            "power.constant.supply_w": 120.0,
            "power.constant.base_load_w": 10.0,
            "compute.capacity.duty_cycle_ratio": 0.5,
            "sensor.conical.duty_cycle_ratio": 0.2,
            "sensor.conical.half_angle_deg": 30.0,
        }), [])

    def test_relation_violation_reports_both_sides(self):
        issues = self.rules.check({
            "power.constant.supply_w": 5.0,
            "power.constant.base_load_w": 10.0,
        })
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["path"], "$.power.constant.base_load_w")
        self.assertIn("must be <=", issues[0]["message"])

    def test_sum_budget_and_range_fire_on_boundaries(self):
        issues = self.rules.check({
            "compute.capacity.duty_cycle_ratio": 0.7,
            "sensor.conical.duty_cycle_ratio": 0.6,
            "sensor.conical.half_angle_deg": 95.0,
        })
        messages = [issue["message"] for issue in issues]
        self.assertTrue(any("allocation sums to 1.3" in m for m in messages))
        self.assertTrue(any("must be <= 90" in m for m in messages))

    def test_requires_and_required_if_are_enforced(self):
        requires = self.rules.check({"power.constant.base_load_w": 10.0})
        self.assertTrue(any("requires 'power.constant.supply_w'" in i["message"]
                            for i in requires))
        required_if = self.rules.check(
            {"sensor.conical.half_angle_deg": 30.0})
        self.assertTrue(any("is required by" in i["message"] for i in required_if))
        # The same map with the required present is clean.
        self.assertEqual(self.rules.check(
            {"sensor.conical.half_angle_deg": 30.0, "power.constant.supply_w": 5.0}), [])

    def test_one_of_counts_declared_fields_only(self):
        self.assertEqual(self.rules.check({"power.constant.supply_w": 5.0}), [])
        issues = self.rules.check({
            "power.constant.supply_w": 5.0,
            "power.solar-battery.array_area_m2": 2.0,
        })
        self.assertTrue(any("expected exactly 1" in i["message"] for i in issues))

    def test_absent_fields_mean_defaults_not_violations(self):
        self.assertEqual(self.rules.check({}), [])

    def test_scope_selected_rules_and_short_keys(self):
        scoped = self.rules.check(
            {"base_load_w": 1e9, "supply_w": 120.0}, scope="power.constant")
        self.assertTrue(any("must be <=" in i["message"] for i in scoped))
        # The same values without a scope are interpreted as alien keys.
        self.assertEqual(self.rules.check({"base_load_w": 1e9, "supply_w": 120.0}), [])

    def test_model_support_category_is_reported_not_enforced(self):
        """A physical rule failing is a bug; a model_support rule is a warning."""
        actual = [rule for rule in builtin_rules().to_dict()["rules"]]
        self.assertTrue(all(rule["category"] == "physical" for rule in actual))
        # A mixed registry still evaluates the category flag transparently.
        registry = make_registry(("a.one.x_m", "m", 1.0))
        rules = ConstraintRegistry([
            RangeRule(id="far", kind="range", category="model_support",
                      field="a.one.x_m", maximum=0.5),
        ], registry=registry)
        issues = rules.check({"a.one.x_m": 5.0})
        # The value is reported, and the caller — not the checker — is what
        # decides between refusing and warning on model_support rules.
        self.assertIn("must be <=", issues[0]["message"])


class TestTransactions(unittest.TestCase):
    def setUp(self):
        self.rules = builtin_rules()

    def test_a_valid_edit_is_transparent(self):
        current = {"power.constant.supply_w": 100.0, "power.constant.base_load_w": 10.0}
        self.assertEqual(
            self.rules.check_transaction(current, {**current, "power.constant.base_load_w": 50.0}),
            [])

    def test_a_bad_edit_returns_diagnostics_and_changes_nothing(self):
        current = {
            "power.constant.supply_w": 100.0,
            "power.constant.base_load_w": 10.0,
            "power.solar-battery.array_area_m2": 2.0,
        }
        candidate = {
            "power.constant.supply_w": 5.0,
            "power.constant.base_load_w": 50.0,
            "power.solar-battery.array_area_m2": 2.0,
        }
        issues = self.rules.check_transaction(current, candidate)
        self.assertTrue(any("must be <=" in i["message"] for i in issues))
        self.assertEqual(current["power.constant.base_load_w"], 10.0)

    def test_removed_fields_fall_back_to_their_registry_default(self):
        current = {"power.constant.supply_w": 100.0, "power.constant.base_load_w": 100.0}
        issues = self.rules.check_transaction(current, {})
        registry = builtin_registry()
        # The default load is within the default supply, so reverting both
        # fields to defaults clears the previously-violating pair.
        self.assertEqual(issues, [])
        self.assertEqual(registry.get("power.constant.base_load_w").default,
                         registry.effective_values("power.constant", {})["base_load_w"])


class TestBuiltinRules(unittest.TestCase):
    def test_builtin_rules_hold_for_reference_defaults(self):
        registry = builtin_registry()
        for owner in registry.owners():
            effective = registry.effective_values(owner, {})
            self.assertEqual(builtin_rules(registry).check(effective, scope=owner, path=f"$/{owner}"),
                             [], f"builtin defaults violate the builtin rules for {owner}")

    def test_check_parameters_helpers(self):
        issues = check_parameters({"power.constant.supply_w": 1.0,
                                   "power.constant.base_load_w": 2.0})
        self.assertTrue(issues)
        self.assertEqual(check_parameters({}, scope="sensor.conical"), [])

    def test_every_builtin_rule_is_declarative_data(self):
        payload = builtin_rules().to_dict()
        self.assertGreaterEqual(payload["count"], 4)
        for rule in payload["rules"]:
            self.assertIn(rule["kind"], ("relation", "one-of", "sum-budget", "range"))
        # No embedded code anywhere: the only supported rule kinds are the
        # six operators checked by comparison code.
        blob = repr(payload)
        self.assertNotIn("eval", blob)
        self.assertNotIn("exec", blob)


if __name__ == "__main__":
    unittest.main()
