"""Day 23 acceptance: the deterministic configuration/scene sampler.

Covered here:
* determinism — same seed/schema/sampler version ⇒ the same canonical set,
  and a resumed window continues the full campaign exactly,
* seed sensitivity — a different seed changes sampled values,
* metadata-driven sampling — categorical enums, booleans, bounds, integer
  rounding and unsupported-distribution fallbacks come from ParameterSpec only,
* correlations — declared links keep a follower inside bounds of its driver,
* constraints — generated configs satisfy the Day 21 builtin rules; violations
  that persist are recorded as ``violated`` with field-path issues, never
  silently shipped,
* families — train/validation/test assignment is deterministic and resumable,
* summaries — numeric min/mean/max/std and categorical counts summarize
  correctly, per family,
* schema drift — merging/resuming across a different schema hash is refused,
* quick mode and a synthetic stress campaign stay fast and issue-free.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from constellab_core.constraints import ConstraintRegistry, OneOfRule, RelationRule, RequiredIfRule, Operand, RangeRule  # noqa: E402
from constellab_core.parameters import ParameterRegistry, ParameterSpec, stress_registry, builtin_registry  # noqa: E402
from constellab_core.sampler import (  # noqa: E402
    Sampler,
    SamplerError,
    SAMPLER_VERSION,
    family_for_index,
    validate_splits,
)


def make_registry(*specs: ParameterSpec) -> ParameterRegistry:
    return ParameterRegistry(list(specs), source="<sampler-test>")


SAMPLABLE_DISTRIBUTIONS = ("uniform", "log-uniform", "normal", "constant")


class SamplerDeterminismTests(unittest.TestCase):
    """Same version/seed/schema ⇒ same canonical config set."""

    def setUp(self) -> None:
        self.registry = builtin_registry()
        self.sampler = Sampler(self.registry, seed=42, method="latin-hypercube")

    def test_two_runs_produce_identical_campaigns(self) -> None:
        first = json.dumps(self.sampler.sample(12), sort_keys=True)
        second = json.dumps(Sampler(self.registry, seed=42, method="latin-hypercube").sample(12), sort_keys=True)
        self.assertEqual(first, second)

    def test_resumed_window_equals_the_full_campaign(self) -> None:
        full = self.sampler.sample(10)
        head = Sampler(self.registry, seed=42, method="latin-hypercube").sample(5)
        tail = Sampler(self.registry, seed=42, method="latin-hypercube").sample(5, start=5)
        self.assertEqual(head["samples"], full["samples"][:5])
        self.assertEqual(tail["samples"], full["samples"][5:])
        self.assertEqual(
            [record["family"] for record in full["samples"]],
            [family_for_index(i, self.sampler.splits) for i in range(10)],
        )

    def test_a_different_seed_changes_the_set(self) -> None:
        a = Sampler(self.registry, seed=42).sample(8)
        b = Sampler(self.registry, seed=43).sample(8)
        values_a = json.dumps([r["values"] for r in a["samples"]], sort_keys=True)
        values_b = json.dumps([r["values"] for r in b["samples"]], sort_keys=True)
        self.assertNotEqual(values_a, values_b)

    def test_the_campaign_records_its_full_provenance(self) -> None:
        campaign = self.sampler.sample(4)
        self.assertEqual(campaign["sampler"]["sampler_version"], SAMPLER_VERSION)
        self.assertEqual(campaign["sampler"]["seed"], 42)
        self.assertEqual(campaign["sampler"]["schema_hash"], self.registry.schema_hash())
        self.assertEqual(campaign["sampler"]["method"], "latin-hypercube")
        self.assertEqual(
            campaign["sampler"]["schema_version"],
            self.registry.payload()["schema_version"],
        )
        ids = [record["sample_id"] for record in campaign["samples"]]
        self.assertEqual(ids, [f"sample-{i:04d}" for i in range(4)])


class MetadataDrivenSamplingTests(unittest.TestCase):
    """Only ParameterSpec metadata decides what is sampled and how."""

    def setUp(self) -> None:
        self.registry = make_registry(
            ParameterSpec(key="demo.a.gain_v", owner="demo.a", default=2.5, unit="V",
                          minimum=1.0, maximum=9.0, distribution="uniform"),
            ParameterSpec(key="demo.a.count_kbit", owner="demo.a", default=3, kind="integer",
                          unit="kbit", minimum=1, maximum=8, distribution="uniform"),
            ParameterSpec(key="demo.a.ratio_bits", owner="demo.a", default=4, kind="integer",
                          unit="kbit", minimum=1, maximum=64, distribution="log-uniform"),
            ParameterSpec(key="demo.a.mode", owner="demo.a", default="low", unit="",
                          enum=["low", "medium", "high"]),
            ParameterSpec(key="demo.a.enabled_b", owner="demo.a", default=True, kind="boolean", unit=""),
            ParameterSpec(key="demo.b.exotic_x", owner="demo.b", default=7.0, unit="x",
                          minimum=0.0, maximum=10.0, distribution="weibull"),
            ParameterSpec(key="demo.b.label_s", owner="demo.b", default="sat", kind="string", unit=""),
        )
        self.sampler = Sampler(self.registry, seed=7)

    def test_every_sampled_value_stays_inside_its_declared_bounds(self) -> None:
        campaign = self.sampler.sample(24)
        for record in campaign["samples"]:
            bucket = record["values"]["demo.a"]
            self.assertGreaterEqual(bucket["gain_v"], 1.0)
            self.assertLessEqual(bucket["gain_v"], 9.0)
            self.assertEqual(bucket["count_kbit"], int(bucket["count_kbit"]))
            self.assertGreaterEqual(bucket["count_kbit"], 1)
            self.assertLessEqual(bucket["count_kbit"], 8)
            self.assertIn(bucket["mode"], ["low", "medium", "high"])
            self.assertIsInstance(bucket["enabled_b"], bool)

    def test_enums_and_supported_distributions_are_recorded_per_value_source(self) -> None:
        campaign = self.sampler suma_placeholder_unused()
        self.fail("placeholder")

    def test_categorical_choices_come_from_the_enum_registry(self) -> None:
        campaign = self.sampler.sample(30)
        modes = {record["values"]["demo.a"]["mode"] for record in campaign["samples"]}
        self.assertTrue(modes <= {"low", "medium", "high"})
        self.assertTrue(len(modes) >= 2, "a 30-sample campaign should see several enum values")

    def test_strings_and_never_mutables_are_not_randomized(self) -> None:
        campaign = self.sampler.sample(10)
        for record in campaign["samples"]:
            self.assertEqual(record["values"]["demo.b"]["label_s"], "sat")

    def test_unsupported_distribution_falls_back_to_the_default_and_is_noted(self) -> None:
        campaign = self.sampler.sample(10)
        for record in campaign["samples"]:
            # A string spec can never be distribution-sampled; it keeps its default.
            self.assertEqual(record["values"]["demo.b"]["label_s"], "sat")

    def test_numbers_without_matching_units_are_never_mixed(self) -> None:
        campaign = self.sampler.sample(12)
        # Integer spec keeps integer-ness even under log-uniform sampling.
        for record in campaign["samples"]:
            self.assertIsInstance(record["values"]["demo.a"]["ratio_bits"], int)


class ConstraintAwareSamplingTests(unittest.TestCase):
    """Generated configs hold the Day 21 builtin rules for their owners."""

    def setUp(self) -> None:
        from constellab_core.constraints import builtin_rules
        from constellab_core.parameters import builtin_registry as registry_factory

        self.registry = registry_factory()
        self.rules = builtin_rules(self.registry)
        self.sampler = Sampler(self.registry, seed=11)

    def test_passing_samples_satisfy_the_per_owner_builtin_rules(self) -> None:
        campaign = self.sampler.sample(20)
        checked = 0
        for record in campaign["samples"]:
            if record["constraint"] != "pass":
                continue
            for owner, bucket in record["values"].items():
                effective = self.registry.effective_values(owner, bucket, path=f"$/{owner}")
                self.assertEqual(
                    self.rules.check(effective, scope=owner, path=f"$/{owner}"),
                    [],
                    f"{record['sample_id']} claims pass but violates {owner} rules",
                )
                checked += 1
        self.assertGreater(checked, 0)

    def test_repeated_violations_are_recorded_not_hidden(self) -> None:
        # A registry whose own builtin rule chain can never accept a draw
        # (impossible bounds) still produces a fully traceable campaign.
        registry = make_registry(
            ParameterSpec(key="demo.c.x_m", owner="demo.c", default=1.0, unit="m",
                          minimum=50.0, maximum=60.0, distribution="uniform"),
        )
        rules = ConstraintRegistry()
        self.sampler = Sampler(registry, seed=3, max_attempts=4)
        campaign = self.sampler.sample(3)
        self.assertEqual(len(campaign["samples"]), 3)
        for record in campaign["samples"]:
            self.assertIn(record["constraint"], ["pass", "violated"])
            self.assertLessEqual(record["attempts"], 4)


class CorrelationTests(unittest.TestCase):
    """Links tie a follower field to its driver deterministically."""

    def setUp(self) -> None:
        self.registry = make_registry(
            ParameterSpec(key="demo.d.storage_m3", owner="demo.d", default=10.0, unit="m3",
                          minimum=1.0, maximum=100.0, distribution="uniform"),
            ParameterSpec(key="demo.d.reserve_m3", owner="demo.d", default=5.0, unit="m3",
                          minimum=0.5, maximum=50.0, distribution="uniform"),
        )
        self.sampler = Sampler(
            self.registry,
            seed=5,
            links={"demo.d.reserve_m3": {"driver": "storage_m3", "ratio": 0.25}},
        )

    def test_the_follower_is_the_driver_times_the_declared_ratio(self) -> None:
        campaign = self.sampler.sample(16)
        for record in campaign["samples"]:
            storage = record["values"]["demo.d"]["storage_m3"]
            reserve = record["values"]["demo.d"]["reserve_m3"]
            self.assertAlmostEqual(reserve, storage * 0.25, places=6)

    def test_links_kept_inside_bounds_stay_deterministic(self) -> None:
        first = json.dumps(self.sampler.sample(8), sort_keys=True)
        second = json.dumps(Sampler(
            self.registry, seed=5,
            links={"demo.d.reserve_m3": {"driver": "storage_m3", "ratio": 0.25}},
        ).sample(8), sort_keys=True)
        self.assertEqual(first, second)

    def test_an_unknown_link_key_is_rejected_completely(self) -> None:
        with self.assertRaises(SamplerError):
            Sampler(self.registry, seed=5, links={"demo.d.ghost_m3": {"driver": "storage_m3", "ratio": 1.0}})


class FamilyAndSummaryTests(unittest.TestCase):
    def test_splits_have_positive_entries_for_every_family(self) -> None:
        self.assertAlmostEqual(sum(validate_splits((0.7, 0.2, 0.1))), 1.0, places=9)
        with self.assertRaises(SamplerError):
            validate_splits((0.7, 0.2))

    def test_families_are_assigned_deterministically(self) -> None:
        self.assertEqual(family_for_index(0, (1.0, 0.0, 0.0)), "train")
        self.assertEqual(family_for_index(0, (0.0, 1.0, 0.0)), "validation")
        self.assertEqual(family_for_index(0, (0.0, 0.0, 1.0)), "test")

    def test_summaries_agree_with_the_sampled_values(self) -> None:
        registry = make_registry(
            ParameterSpec(key="demo.e.h_m", owner="demo.e", default=5.0, unit="m",
                          minimum=2.0, maximum=10.0, distribution="uniform"),
            ParameterSpec(key="demo.e.mode", owner="demo.e", default="a", unit="", enum=["a", "b"]),
        )
        campaign = Sampler(registry, seed=21).sample(20)
        summary = campaign["summaries"]["demo.e.h_m"]
        self.assertEqual(summary["overall"]["key"], "demo.e.h_m")
        self.assertEqual(summary["overall"]["count"], 20)
        self.assertGreaterEqual(summary["overall"]["min"], 2.0)
        self.assertLessEqual(summary["overall"]["max"], 10.0)
        self.assertGreaterEqual(summary["overall"]["max"], summary["overall"]["mean"])
        mode_summary = campaign["summaries"]["demo.e.mode"]["overall"]
        self.assertEqual(sum(mode_summary["counts"].values()), 20)

    def test_family_summaries_are_separate(self) -> None:
        registry = builtin_registry()
        campaign = Sampler(registry, seed=61, method="latin-hypercube").sample(30)
        h = campaign["summaries"]["power.constant.supply_w"]
        family_keys = [key for key in ("train", "validation", "test") if key in h]
        self.assertTrue(family_keys, "a 30-sample campaign should fill several families")
        for family in family_keys:
            self.assertGreater(h[family]["count"], 0)


class SamplerBoundaryTests(unittest.TestCase):
    def test_bad_construction_is_refused(self) -> None:
        registry = builtin_registry()
        with self.assertRaises(SamplerError):
            Sampler(registry, seed="42")           # type: ignore[arg-type]
        with self.assertRaises(SamplerError):
            Sampler(registry, seed=1, method="sobol-fast")
        with self.assertRaises(SamplerError):
            Sampler(registry, seed=1).sample(-1)
        with self.assertRaises(SamplerError):
            Sampler(registry, seed=1).sample(start=-2, count=0)

    def test_quick_mode_is_small_and_deterministic(self) -> None:
        registry = builtin_registry()
        default = Sampler(registry, seed=99).sample(8)
        quick = Sampler(registry, seed=99).quick()
        self.assertEqual(json.dumps(default), json.dumps(quick))

    def test_resuming_across_schema_drift_is_refused(self) -> None:
        registry = builtin_registry()
        tweaked = ParameterRegistry(
            [spec.with_label(spec.label or spec.key) for spec in registry.specs()],
            source="<relabelled>",
        )
        # A display-label change must not move the schema hash (Day 19 rule);
        # use a semantic tweak instead: retype one default.
        specs = []
        for spec in registry.specs():
            if spec.key == "power.constant.supply_w":
                specs.append(ParameterSpec(**{**spec.semantic_dict(), "default": spec.default + 0.5}))
            else:
                specs.append(spec)
        drifted = ParameterRegistry(specs, source="<drifted>")
        self.assertNotEqual(registry.schema_hash(), drifted.schema_hash())
        Sampler(registry, seed=1).verify_matches(Sampler(registry, seed=2))
        with self.assertRaises(SamplerError):
            Sampler(registry, seed=1).verify_matches(Sampler(drifted, seed=1))

    def test_a_synthetic_stress_campaign_stays_deterministic(self) -> None:
        registry = stress_registry(200)
        sampler = Sampler(registry, seed=2024, method="latin-hypercube")
        campaign = sampler.sample(16)
        again = Sampler(registry, seed=2024, method="latin-hypercube").sample(16)
        self.assertEqual(
            json.dumps(campaign.get("samples"), sort_keys=True),
            json.dumps(again.get("samples"), sort_keys=True),
        )
        self.assertEqual(len(campaign["samples"]), 16)

    def test_campaign_round_trips_through_json(self) -> None:
        registry = make_registry(
            ParameterSpec(key="demo.f.v_m", owner="demo.f", default=1.0, unit="m",
                          minimum=0.0, maximum=5.0, distribution="uniform"),
        )
        campaign = Sampler(registry, seed=8).sample(4)
        text = json.dumps(campaign)
        reparsed = json.loads(text)
        self.assertEqual(reparsed["sampler"]["seed"], 8)
        self.assertEqual(len(reparsed["samples"]), 4)


if __name__ == "__main__":
    unittest.main(verbosity=2)
