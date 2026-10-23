"""Day 25 acceptance: EO targets + geospatial event-source plugin registry.

* target validation: geography ranges, time intervals, urgency/confidence,
  lifecycle (`is_active`), duplicate ids in a trace,
* separation of ground truth: `observable_view` never carries `truth`,
* deterministic traces: same seed/spec ⇒ identical JSON; different seed differs,
* plugin sources: multiple activated sources compose without editing the event
  loop; registration duplicates and unknown names fail loudly,
* truth stays out of the serializable observable payload even for the whole
  trace view.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from constellab_core.targets import (  # noqa: E402
    SUPPORTED_EVENT_KINDS,
    EventSourceRegistry,
    EventTarget,
    TargetError,
    active_trace,
    observable_events,
    trace_report,
    validate_trace,
)


def make_target(**overrides: object) -> EventTarget:
    base = {
        "id": "fire-01",
        "kind": "hotspot",
        "lat_deg": 12.0,
        "lon_deg": -30.0,
        "start_s": 100.0,
        "end_s": 200.0,
        "urgency": 5,
        "confidence": 0.8,
        "requirements": {"min_confidence": 0.5},
        "truth": {"intensity_mw": 12.5},
    }
    base.update(overrides)  # type: ignore[arg-type]
    return EventTarget(**base)  # type: ignore[arg-type]


class TargetValidationTests(unittest.TestCase):
    def test_geographic_and_time_ranges_are_enforced(self) -> None:
        with self.assertRaises(TargetError):
            make_target(lat_deg=91.0)
        with self.assertRaises(TargetError):
            make_target(lon_deg=180.5)
        with self.assertRaises(TargetError):
            make_target(end_s=100.0)      # end == start
        with self.assertRaises(TargetError):     # type: ignore[call-overload]
            make_target(urgency=0)
        with self.assertRaises(TargetError):
            make_target(urgency=6)
        with self.assertRaises(TargetError):
            make_target(confidence=1.5)

        self.assertEqual(SUPPORTED_EVENT_KINDS, ("hotspot", "flood-region", "change-detection"))

    def test_lifecycle_and_active_trace(self) -> None:
        a = make_target(id="a", start_s=0.0, end_s=10.0)
        b = make_target(id="b", start_s=20.0, end_s=30.0)
        c = make_target(id="c", start_s=5.0, end_s=500.0)
        self.assertFalse(a.is_active(10.0))
        self.assertTrue(c.is_active(10.0))
        active = active_trace([a, b, c], time_s=25.0)
        self.assertEqual([t.id for t in active], ["b", "c"])

    def test_validate_trace_flags_duplicate_ids(self) -> None:
        trace = [make_target(id="dup"), make_target(id="dup", start_s=300.0, end_s=400.0)]
        issues = validate_trace(trace)
        self.assertEqual(len(issues), 1)
        self.assertIn("duplicate", issues[0]["message"])


class TruthSeparationTests(unittest.TestCase):
    def observable_view(self, target: EventTarget) -> dict:
        return target.observable_view(50.0)

    def test_observable_view_has_no_truth(self) -> None:
        target = make_target()
        view = target.observable_view()
        self.assertNotIn("truth", view)
        dumped = json.dumps(view)
        self.assertNotIn("intensity_mw", dumped)
        # Observable metadata remains available for consumer UI.
        self.assertEqual(view["urgency"], 5)
        self.assertEqual(view["requirements"], {"min_confidence": 0.5})

    def test_observable_events_carries_no_truth_at_any_time(self) -> None:
        trace = [make_target(id=f"t-{i}") for i in range(3)]
        payload = observable_events(trace, time_s=150.0)
        self.assertGreater(len(payload), 0)
        dumped = json.dumps(payload)
        self.assertNotIn("truth", dumped)


class DeterministicTraceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = EventSourceRegistry()
        self.registry.activate_all()

    def test_same_seed_and_spec_produce_the_same_trace(self) -> None:
        spec = {"hotspot": {"count": 6, "horizon_s": 3600.0}}
        first = [t.to_dict() for t in self.registry.generate(seed=42, config=spec)]
        second = [t.to_dict() for t in self.registry.generate(seed=42, config=spec)]
        self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))
        # Per-source specs only shape their own source; every activated source
        # still contributes, and each id carries its source prefix.
        ids = [t["id"] for t in first]
        for prefix in ("hotspot.", "flood-region.", "change-detection."):
            self.assertTrue(any(i.startswith(prefix) for i in ids), prefix)

    def test_different_seeds_differ(self) -> None:
        first = json.dumps([t.to_dict() for t in self.registry.generate(seed=1)], sort_keys=True)
        second = json.dumps([t.to_dict() for t in self.registry.generate(seed=2)], sort_keys=True)
        self.assertNotEqual(first, second)

    def test_sources_embed_their_kind_and_time_spans(self) -> None:
        targets = self.registry.generate(seed=7)
        report = trace_report(targets)
        self.assertEqual(report["kinds"]["hotspot"], 4)
        self.assertEqual(report["kinds"]["flood-region"], 2)
        self.assertEqual(report["kinds"]["change-detection"], 3)
        self.assertEqual(report["count"], 9)
        self.assertGreater(report["span_s"][1], report["span_s"][0])
        for target in targets:
            self.assertGreaterEqual(target.urgency, 1)
            self.assertLessEqual(target.urgency, 5)
            self.assertGreater(target.end_s, target.start_s)


class EventSourceRegistryTests(unittest.TestCase):
    def build(self) -> EventSourceRegistry:
        return EventSourceRegistry()

    def test_register_activate_generate(self) -> None:
        registry = self.build()
        self.assertEqual(registry.registered(), ["change-detection", "flood-region", "hotspot"])
        self.assertEqual(registry.activated(), [])
        registry.activate("hotspot")
        self.assertEqual(registry.activated(), ["hotspot"])
        ids = [t.id for t in registry.generate(seed=99)]
        self.assertTrue(ids)
        self.assertTrue(all(i.startswith("hotspot.") for i in ids))

    def test_duplicate_registration_fails_loudly(self) -> None:
        registry = self.build()
        with self.assertRaises(TargetError):
            registry.register("hotspot", lambda rng, spec: [])

    def test_unknown_name_and_unactivated_registry_raise(self) -> None:
        registry = self.build()
        with self.assertRaises(TargetError):
            registry.activate("ghost")
        with self.assertRaises(TargetError):
            registry.generate(seed=1)
        with self.assertRaises(TargetError):
            registry.generate_source("ghost", seed=1)

    def test_multiple_sources_compose_without_event_loop_edits(self) -> None:
        registry = self.build()
        registry.activate_all(["hotspot", "flood-region"])
        targets = registry.generate(seed=5, config={"hotspot": {"count": 2}})
        kinds = {t.kind for t in targets}
        self.assertEqual(kinds, {"hotspot", "flood-region"})
        ids = [t.id for t in targets]
        self.assertEqual(len(ids), len(set(ids)), "ids stay unique across sources")

    def test_a_third_party_style_source_registers_and_runs(self) -> None:
        registry = self.build()

        def aurora_source(rng, spec):  # type: ignore[no-untyped-def]
            return [
                EventTarget(
                    id=f"aurora-{index}",
                    kind="change-detection",
                    lat_deg=60 + rng.random() * 5,
                    lon_deg=rng.uniform(-180, 180),
                    start_s=0.0,
                    end_s=spec.get("horizon_s", 1000.0),
                    urgency=1,
                    truth={"kp_index": 7},
                )
                for index in range(2)
            ]

        registry.register("aurora", aurora_source)
        registry.activate("aurora")
        targets = registry.generate(seed=3)
        self.assertEqual([t.id for t in targets], ["aurora.aurora-0", "aurora.aurora-1"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
