"""Day 29 acceptance tests: geometry-driven contact opportunities and topology."""

import json
import unittest

from constellab_core import contacts
from constellab_core.config import load_config
from constellab_core.contacts import (
    ContactError,
    LinkConfig,
    connected_components,
    contact_plan,
    contact_plan_for_config,
    contact_report,
    is_connected,
    link_geometry,
    link_model,
    registered_link_models,
    register_link_model,
    topology_at,
    topology_scenario,
    unregister_link_model,
)


def plan_for(kind: str, *, horizon_s: float = 5_400.0, step_s: float = 30.0,
             link_overrides: dict | None = None) -> tuple[object, list, list[str]]:
    spec = topology_scenario(kind)
    config = load_config(spec["config"])
    values = {**spec["link"], **(link_overrides or {})}
    plan = contact_plan_for_config(
        config, link_key=values["model"], link_values=values,
        horizon_s=horizon_s, step_s=step_s,
    )
    return config, plan, [satellite.id for satellite in config.satellites]


class LinkRegistryTests(unittest.TestCase):
    def test_builtin_models_are_registered(self) -> None:
        self.assertEqual(set(registered_link_models()), {"link.uhf", "link.optical"})
        payload = contacts.link_models_payload()
        self.assertEqual(payload["version"], contacts.CONTACT_VERSION)
        self.assertTrue(payload["fidelity"])

    def test_unknown_model_is_rejected(self) -> None:
        with self.assertRaises(ContactError) as caught:
            link_model("link.telepathy")
        self.assertIn("link.optical", str(caught.exception))

    def test_defaults_merge_with_scenario_overrides(self) -> None:
        optical = link_model("link.optical").config({})
        self.assertEqual(optical.max_range_km, 4_000.0)
        tuned = link_model("link.optical").config({"max_range_km": 900.0})
        self.assertEqual(tuned.max_range_km, 900.0)
        self.assertEqual(tuned.bandwidth_bps, optical.bandwidth_bps)

    def test_invalid_configuration_is_rejected(self) -> None:
        with self.assertRaises(ContactError):
            LinkConfig(model="link.optical", max_range_km=0.0)
        with self.assertRaises(ContactError):
            LinkConfig(model="link.optical", latency_s=-1.0)

    def test_a_third_party_link_joins_without_core_edits(self) -> None:
        class SbandRelay(contacts.UhfLink):
            key = "link.sband-test"
            label = "S-band test relay"

        register_link_model(SbandRelay())
        try:
            self.assertIn("link.sband-test", registered_link_models())
            config = link_model("link.sband-test").config({"max_range_km": 8_000.0})
            self.assertEqual(config.max_range_km, 8_000.0)
        finally:
            unregister_link_model("link.sband-test")


class LinkGeometryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = LinkConfig(model="link.optical", max_range_km=4_000.0, min_clearance_km=150.0)

    def test_range_boundary_is_inclusive(self) -> None:
        a = (6_978.0, 0.0, 0.0)
        b = (6_978.0, 4_000.0, 0.0)
        geometry = link_geometry(a, b, self.config)
        self.assertAlmostEqual(geometry.range_km, 4_000.0, places=6)
        self.assertTrue(geometry.in_range)
        beyond = link_geometry(a, (6_978.0, 4_001.0, 0.0), self.config)
        self.assertFalse(beyond.in_range)
        self.assertFalse(beyond.visible)
        self.assertEqual(beyond.quality, 0.0)

    def test_earth_blocks_a_pair_on_opposite_sides(self) -> None:
        geometry = link_geometry((6_928.0, 0.0, 0.0), (-6_928.0, 0.0, 0.0), self.config)
        self.assertLess(geometry.clearance_km, 0.0)
        self.assertFalse(geometry.clear)
        self.assertFalse(geometry.visible)

    def test_limb_clearance_boundary(self) -> None:
        radius = contacts.EARTH_EQUATORIAL_RADIUS_KM
        a = (radius + 100.0, 0.0, 0.0)  # 100 km altitude
        b = (radius + 100.0, 200.0, 0.0)
        loose = link_geometry(a, b, LinkConfig(model="link.optical", min_clearance_km=100.0))
        self.assertAlmostEqual(loose.clearance_km, 100.0, places=6)
        self.assertTrue(loose.clear)
        strict = link_geometry(a, b, LinkConfig(model="link.optical", min_clearance_km=150.0))
        self.assertFalse(strict.clear)
        self.assertFalse(strict.visible)

    def test_quality_degrades_with_range(self) -> None:
        near = link_geometry((6_978.0, 0.0, 0.0), (6_978.0, 500.0, 0.0), self.config)
        far = link_geometry((6_978.0, 0.0, 0.0), (6_978.0, 3_500.0, 0.0), self.config)
        self.assertTrue(near.visible and far.visible)
        self.assertGreater(near.quality, far.quality)


class ContactPlanTests(unittest.TestCase):
    def test_plan_is_deterministic(self) -> None:
        first = [item.to_dict() for item in plan_for("intermittently-connected")[1]]
        second = [item.to_dict() for item in plan_for("intermittently-connected")[1]]
        self.assertTrue(first)
        self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))

    def test_plan_order_is_stable_and_pairs_are_sorted(self) -> None:
        _config, plan, nodes = plan_for("fully-connected")
        self.assertEqual(len(plan), len(nodes) * (len(nodes) - 1) // 2)
        for opportunity in plan:
            self.assertLess(opportunity.a_id, opportunity.b_id)

    def test_plan_pairs_come_from_sorted_ids(self) -> None:
        positions = {
            "b": lambda t: (6_978.0, 0.0, 0.0),
            "a": lambda t: (6_978.0, 100.0, 0.0),
        }
        plan = contact_plan(
            positions,
            config=LinkConfig(model="link.optical", max_range_km=1_000.0),
            horizon_s=60.0,
            step_s=30.0,
        )
        self.assertEqual(len(plan), 1)
        self.assertEqual((plan[0].a_id, plan[0].b_id), ("a", "b"))

    def test_link_topology_changes_with_declared_configuration(self) -> None:
        positions = {
            "a": lambda t: (6_978.0, 0.0, 0.0),
            "b": lambda t: (6_978.0, 2_000.0, 0.0),
        }
        short = contact_plan(
            positions, config=LinkConfig(model="link.optical", max_range_km=1_000.0),
            horizon_s=60.0, step_s=30.0,
        )
        long_range = contact_plan(
            positions, config=LinkConfig(model="link.uhf", max_range_km=4_000.0),
            horizon_s=60.0, step_s=30.0,
        )
        self.assertEqual(short, [])
        self.assertEqual(len(long_range), 1)
        self.assertTrue(is_connected(["a", "b"], [long_range[0].pair]))


class TopologyTests(unittest.TestCase):
    def test_three_reference_arrangements_behave_as_declared(self) -> None:
        config, plan, nodes = plan_for("fully-connected")
        report = contact_report(plan, nodes=nodes, horizon_s=5_400.0, step_s=60.0)
        self.assertTrue(report["always_connected"])
        self.assertEqual(report["link_counts"], [6])

        _config, plan, nodes = plan_for("disconnected")
        report = contact_report(plan, nodes=nodes, horizon_s=5_400.0, step_s=60.0)
        self.assertFalse(report["always_connected"])
        self.assertFalse(report["ever_connected"])
        self.assertEqual(report["link_counts"], [2])
        topology = topology_at(plan, nodes, 600.0)
        self.assertEqual(
            topology["components"],
            [["sat-alpha", "sat-bravo"], ["sat-charlie", "sat-delta"]],
        )

        _config, plan, nodes = plan_for("intermittently-connected")
        report = contact_report(plan, nodes=nodes, horizon_s=5_400.0, step_s=60.0)
        self.assertFalse(report["always_connected"])
        self.assertTrue(report["ever_connected"])
        self.assertEqual(report["link_counts"], [0, 1])

    def test_components_and_connectivity_helpers(self) -> None:
        edges = [("a", "b"), ("c", "d")]
        self.assertEqual(connected_components(["a", "b", "c", "d"], edges), [["a", "b"], ["c", "d"]])
        self.assertFalse(is_connected(["a", "b", "c", "d"], edges))
        self.assertTrue(is_connected(["a", "b"], [("a", "b")]))
        self.assertTrue(is_connected(["a"], []))

    def test_report_carries_fidelity_and_pair_totals(self) -> None:
        _config, plan, nodes = plan_for("fully-connected")
        report = contact_report(plan, nodes=nodes, horizon_s=600.0, step_s=60.0)
        self.assertTrue(report["fidelity"])
        self.assertEqual(len(report["pairs"]), 6)
        for pair in report["pairs"]:
            self.assertGreater(pair["contact_s"], 0.0)
        self.assertEqual(len(report["timeline"]), 11)

    def test_unknown_arrangement_is_rejected(self) -> None:
        with self.assertRaises(ContactError):
            topology_scenario("telepathy")


if __name__ == "__main__":
    unittest.main()
