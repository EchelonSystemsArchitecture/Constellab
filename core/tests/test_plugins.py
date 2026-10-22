"""Day 20 acceptance: the plugin/component lifecycle.

Day 20 is the lifecycle around implementations: plugins declare what they
provide, activation is one ordered pass with loud, actionable diagnostics on
every failure (duplicates, incompatible host versions, broken activation), and
everything a client writes stays data. Pinned here:

* the built-in set activates once at import and never half-way,
* broken plugins register and report precisely instead of crashing startup,
* activation respects (priority, id) order and teardown unwinds it,
* a third-party-style plugin adds a component **without any core change**,
  and a scenario then selects it purely as data.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from constellab_core import plugins  # noqa: E402
from constellab_core.components import (  # noqa: E402
    ComponentError,
    register_component,
    registered_components,
    unregister_component,
)
from constellab_core.config import builtin_scenario, load_config  # noqa: E402
from constellab_core.components import advance_runtime, initial_runtime  # noqa: E402
from constellab_core.plugins import (  # noqa: E402
    HOST_VERSION,
    Plugin,
    PluginError,
    fresh_host,
    host,
    parse_version,
    version_satisfied,
)

BUILTIN_IDS = {plugin.id for plugin in plugins.builtin_plugins()}


class TestVersionGatekeeping(unittest.TestCase):
    def test_version_parsing_is_strict_semver(self):
        self.assertEqual(parse_version("1.0.0"), (1, 0, 0))
        self.assertEqual(parse_version("10.2.13"), (10, 2, 13))
        for bad in ("", "1", "1.0", "1.0.0.1", "v1.0.0", 1.0, None):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    parse_version(bad)  # type: ignore[arg-type]

    def test_host_version_gate(self):
        self.assertTrue(version_satisfied("0.2.0", HOST_VERSION))
        self.assertTrue(version_satisfied(HOST_VERSION, HOST_VERSION))
        self.assertFalse(version_satisfied("99.0.0", HOST_VERSION))
        with self.assertRaises(ValueError):
            version_satisfied("not-semver", HOST_VERSION)


class TestBuiltinActivation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.activation = plugins.activate_builtins()

    def test_builtins_are_registered_and_active_exactly_once(self):
        self.assertEqual(BUILTIN_IDS, {p["id"] for p in self.activation["plugins"]})
        self.assertTrue(all(p["status"] == "active" for p in self.activation["plugins"]))
        self.assertEqual(self.activation["status"], "ok")
        self.assertTrue(plugins.host().activated)

    def test_reactivation_is_idempotent_and_registered_components_stable(self):
        before = registered_components()
        plugins.activate_builtins()
        self.assertEqual(registered_components(), before)
        # Every builtin provides what it registered.
        self.assertEqual(
            {key for p in self.activation["plugins"] for key in p["provides"]},
            set(registered_components()),
        )


class TestPluginRegistrationForHost(unittest.TestCase):
    """Registration pass on the real (builtin-activated) singleton host."""

    def test_duplicate_builtin_id_and_dup_provides_fail_to_register(self):
        duplicate = Plugin(id=sorted(BUILTIN_IDS)[0], version="1.0.0", label="Clone",
                           provides=("probe.noop",))
        entry = host().register_plugin(duplicate)
        self.assertIn("plugin id is already registered", entry.issues[0]["message"])
        # Duplicate provides only counts against actually registered keys.
        current = registered_components()
        entry = plugins.PluginEntry(plugin=Plugin(  # type: ignore[call-arg]
            id="constellab.probe-dupes", version="1.0.0", label="Dupes",
            provides=(current[0],),
        ))
        issues = host().register_plugin(entry.plugin)
        self.assertFalse(entry.plugin.id in {p["id"] for p in host().report()["plugins"]})
        self.assertIn("already registered", issues.issues[0]["message"])

    def test_host_rejects_invalid_plugin_definitions(self):
        probes = (
            (Plugin(id="nonspace", version="1.0.0", label="Bad", provides=("probe.witness",)),
             "id"),
            (Plugin(id="constellab.probe-bad-version", version="nope", label="Bad",
                    provides=("probe.witness",)),
             "version"),
            (Plugin(id="constellab.probe-future", version="1.0.0", label="Bad",
                    provides=("probe.witness",), min_host_version="99.0.0"),
             "min_host_version"),
            (Plugin(id="constellab.probe-empty", version="1.0.0", label="Bad", provides=()),
             "provides"),
        )
        for plugin, expected_field in probes:
            with self.subTest(field=expected_field):
                entry = host().register_plugin(plugin)
                paths = [issue["path"] for issue in entry.issues]
                self.assertTrue(any(expected_field in path for path in paths), paths)

    def test_hot_plugin_registration_touches_nothing_until_activation(self):
        before = registered_components()
        entry = host().register_plugin(Plugin(
            id="constellab.probe-hot", version="1.1.0",
            label="Probe hot",
            provides=("demo.probe-hot",),
            activate=lambda: register_component(type(
                "HotProbe", (object,),
                {"key": "demo.probe-hot", "label": "Hot probe", "kind": "sensor",
                 "stage": 30, "assumptions": (),
                     "initial_state": staticmethod(lambda params: {}),
                "step": lambda state, params, context: None},
            )()),
        ))
        self.assertEqual(entry.issues, [])
        self.assertEqual(entry.status, "registered")
        self.assertEqual(registered_components(), before)  # not yet active
        host().activate_all()  # activates everything, order pinned below
        self.assertIn("demo.probe-hot", registered_components())
        self.addCleanup(unregister_component, "demo.probe-hot")


class TestPluginLifecycleOnFreshHost(unittest.TestCase):
    def setUp(self):
        self.plugins = fresh_host()

    def _activated_probe(self, key="sensor.probe"):
        def activate():
            register_component(type(
                "Probe", (object,),
                {"key": key, "label": "Probe", "kind": "sensor", "stage": 30,
                 "assumptions": (), "initial_state": staticmethod(lambda params: {}),
                 "step": staticmethod(lambda state, params, context: None)},
            )())

        return activate

    def test_activation_order_follows_priority_then_id(self):
        order: list[str] = []
        for priority, pid in ((5, "constellab.probe-late"),
                              (1, "constellab.probe-early"),
                              (1, "constellab.probe-aa")):
            self.plugins.register_plugin(Plugin(
                id=pid, version="1.0.0", label=pid, provides=("probe.witness",),
                priority=priority,
                activate=lambda pid=pid: order.append(pid),  # type: ignore[misc]
            ))
        self.plugins.activate_all()
        self.assertEqual(order, ["constellab.probe-aa", "constellab.probe-early",
                                 "constellab.probe-late"])

    def test_failed_activation_names_the_cause_and_keeps_the_host(self):
        watched: list[str] = []

        def broken():
            watched.append("ran")
            raise RuntimeError("sensor array offline")

        self.plugins.register_plugin(Plugin(
            id="constellab.probe-broken", version="1.0.0", label="Broken",
            provides=("probe.witness",), priority=10, activate=broken,
        ))
        self.plugins.register_plugin(Plugin(
            id="constellab.probe-after", version="1.0.0", label="After",
            provides=("probe.later",), priority=20,
            activate=lambda: watched.append("later"),
        ))
        report = self.plugins.activate_all()
        statuses = {entry["id"]: entry["status"] for entry in report}
        self.assertEqual(statuses, {"constellab.probe-broken": "failed",
                                    "constellab.probe-after": "active"})
        self.assertEqual(watched, ["ran", "later"])  # later pieces still run
        diagnostic = self.plugins.report()
        self.assertEqual(diagnostic["status"], "degraded")
        found = {p["id"]: p for p in diagnostic["plugins"]}
        broken = found["constellab.probe-broken"]
        issues = " ".join(issue["message"] for issue in broken["issues"])
        self.assertIn("activation failed", issues)
        self.assertIn("sensor array offline", issues)
        self.assertEqual(found["constellab.probe-after"]["status"], "active")

    def test_teardown_unwinds_in_reverse_order_and_is_fail_safe(self):
        order: list[str] = []

        def mark(tick):
            def callback():
                order.append(tick)
            return callback

        def raise_for(pid):
            def callback():
                order.append("-" + pid)
                raise RuntimeError("must not mask shutdown")
            return callback

        self.plugins.register_plugin(Plugin(
            id="constellab.probe-first", version="1.0.0", label="First",
            provides=("probe.witness",), priority=1,
            activate=mark("+first"), teardown=mark("-first"),
        ))
        self.plugins.register_plugin(Plugin(
            id="constellab.probe-second", version="1.0.0", label="Second",
            provides=("probe.witness",), priority=2,
            activate=mark("+second"), teardown=raise_for("constellab.probe-second"),
        ))
        self.plugins.activate_all()
        self.assertEqual(order, ["+first", "+second"])
        self.plugins.shutdown_all()
        # Teardown order is reverse activation and a raising teardown cannot
        # mask the shutdown of the remaining plugins.
        self.assertEqual(order,
                         ["+first", "+second", "-constellab.probe-second", "-first"])
        self.assertTrue(all(entry.status == "registered" for entry in self.plugins.entries()))

    def test_plugins_only_register_data_through_keys(self):
        """Client configs stay data: a scenario selects keys, never executes code."""
        self.plugins.register_plugin(Plugin(
            id="constellab.probe-kitchen", version="1.0.0", label="Kitchen timer",
            provides=("demo.kitchen-timer",), priority=5,
            activate=self._activated_probe("demo.kitchen-timer"),
        ))
        self.plugins.activate_all()
        config = load_config({
            **builtin_scenario("visual-orbit-demo").to_dict(),
            "satellites": [{
                "id": "sat-kitchen",
                "components": [{"type": "demo.kitchen-timer"}],
                "orbit": builtin_scenario("visual-orbit-demo").satellites[0].orbit.to_dict(),
            }],
        })
        runtime = initial_runtime(config)
        advance_runtime(
            config, runtime, time_s=5.0, dt_s=5.0,
            positions={"sat-kitchen": (0.0, 0.0, 0.0)},
        )
        self.assertIn("demo.kitchen-timer", registered_components())
        self.assertIn("demo.kitchen-timer", runtime["sat-kitchen"].state)
        self.addCleanup(unregister_component, "demo.kitchen-timer")


def raise_always():  # pragma: no cover - retained when more probes are needed
    raise AssertionError("unused")


if __name__ == "__main__":
    unittest.main()
