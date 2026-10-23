"""Day 24 acceptance: the automated G1 configurable-foundation gate report.

The report is *generated*, not asserted from thin air: ``generate_report``
re-runs every registry stress, config load, valid/invalid example, unconsumed
field audit, constraint transaction and sampler probe, then the report's own
content is cross-checked here. The artifact is persisted to
``benchmarks/g1-acceptance.json``.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from constellab_core.g1 import generate_report, write_report  # noqa: E402
from constellab_core.parameters import builtin_registry  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


class G1ReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = generate_report()
        cls.registry = builtin_registry()

    def test_the_report_names_the_schema_and_counts_every_registry(self) -> None:
        self.assertEqual(self.report["report_version"], "g1-acceptance-1")
        self.assertEqual(self.report["contract"]["schema_version"], self.registry.payload()["schema_version"])
        self.assertEqual(self.report["contract"]["schema_hash"], self.registry.schema_hash())
        counts = self.report["registries"]
        self.assertGreaterEqual(counts["parameter_count"], 32)
        self.assertGreaterEqual(counts["unit_count"], 30)
        self.assertGreaterEqual(counts["component_count"], 6)
        self.assertGreaterEqual(counts["plugin_count"], 4)
        self.assertGreaterEqual(counts["dynamics_models"], 1)

    def test_high_dimensional_configs_load_within_measured_time(self) -> None:
        stress = self.report["stress"]
        self.assertEqual(stress["registry_parameters"], 1000)
        self.assertGreater(stress["registry_load_ms"], 0.0)
        self.assertGreater(stress["config_1000_load_ms"], 0.0)
        self.assertGreater(stress["component_runtime_1000_ms"], 0.0)
        # Relative bound for this environment: a seconds-long load would be a
        # special-case failure, not a measurement. This is generous on purpose.
        self.assertLess(stress["config_1000_load_ms"], 10_000.0)

    def test_valid_and_invalid_examples_are_both_exercised(self) -> None:
        examples = self.report["examples"]
        self.assertIn("swarm-1000", examples["valid_scenarios"])
        self.assertIn("empty", examples["valid_scenarios"])
        rejected = examples["malformed_fixtures_rejected"]
        self.assertGreaterEqual(len(rejected), 10)
        self.assertIn("unknown operational field", " ".join(rejected))

    def test_behaviour_claims_are_all_true(self) -> None:
        behaviour = self.report["behaviour"]
        self.assertTrue(behaviour["unknown_operational_field_flagged"])
        self.assertTrue(behaviour["transaction_accepts_consistent_edit"])
        self.assertTrue(behaviour["transaction_rejects_bounds_violation"])
        flagged = behaviour["constraint_reputation"]["rejected_paths"]
        self.assertTrue(any("half_angle_deg" in path for path in flagged), flagged)
        self.assertTrue(behaviour["sampler_quick_campaign_recorded"])

    def test_limitations_are_recorded_not_hidden(self) -> None:
        limitations = " ".join(self.report["limitations"]).lower()
        for keyword in ("kepler", "virtual", "registry", "sampling", "measured"):
            self.assertIn(keyword, limitations)

    def test_the_artifact_is_persisted_as_json(self) -> None:
        target = write_report(ROOT / "benchmarks" / "g1-acceptance.json")
        data = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(data["report_version"], self.report["report_version"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
