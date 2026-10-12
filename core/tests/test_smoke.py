"""Smoke tests for the constellab_core package: import, status, CLI exit codes."""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import constellab_core  # noqa: E402
from constellab_core import SCHEMA_VERSION, __version__  # noqa: E402
from constellab_core.__main__ import main  # noqa: E402
from constellab_core.config import ConfigError, validate_config  # noqa: E402
from constellab_core.service import status_payload  # noqa: E402

VALID = {
    "schema_version": SCHEMA_VERSION,
    "scenario_id": "demo",
    "seed": 42,
    "epoch_utc": "2026-10-12T00:00:00Z",
    "satellites": [],
}


class TestPackage(unittest.TestCase):
    def test_package_imports(self):
        self.assertTrue(hasattr(constellab_core, "__version__"))
        self.assertRegex(SCHEMA_VERSION, r"^\d+\.\d+\.\d+$")

    def test_status_payload_shape(self):
        payload = status_payload()
        self.assertEqual(payload["name"], "constellab-core")
        self.assertEqual(payload["version"], __version__)
        self.assertEqual(payload["schema_version"], SCHEMA_VERSION)
        self.assertEqual(payload["status"], "ok")
        self.assertIn("GET /api/status", payload["endpoints"])
        self.assertIn("GET /api/snapshot", payload["endpoints"])


class TestConfigValidation(unittest.TestCase):
    def test_defaults_applied(self):
        effective = validate_config(VALID)
        self.assertEqual(effective["time_scale"], 1.0)
        self.assertEqual(effective["seed"], 42)
        self.assertNotIn("name", effective)

    def test_unknown_field_rejected(self):
        with self.assertRaises(ConfigError) as ctx:
            validate_config({**VALID, "telemetry_rate_hz": 10})
        self.assertEqual(ctx.exception.errors[0]["path"], "$.telemetry_rate_hz")

    def test_non_object_rejected(self):
        with self.assertRaises(ConfigError):
            validate_config([1, 2, 3])


class TestCli(unittest.TestCase):
    def _run(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(argv)
        return code, out.getvalue(), err.getvalue()

    def _tmp_config(self, payload):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            json.dump(payload, fh)
        self.addCleanup(os.unlink, fh.name)
        return fh.name

    def test_status_command(self):
        code, out, _ = self._run(["status"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["status"], "ok")

    def test_status_with_valid_config(self):
        code, _, _ = self._run(["status", "--config", self._tmp_config(VALID)])
        self.assertEqual(code, 0)

    def test_status_with_invalid_config_exits_2(self):
        code, _, err = self._run(["status", "--config", self._tmp_config({**VALID, "seed": -1})])
        self.assertEqual(code, 2)
        self.assertIn("$.seed", err)

    def test_validate_builtin_scenarios(self):
        for name in ("empty", "visual-orbit-demo"):
            code, out, _ = self._run(["validate", name])
            self.assertEqual(code, 0, name)
            self.assertTrue(json.loads(out)["valid"])

    def test_snapshot_command(self):
        code, out, _ = self._run(["snapshot", "visual-orbit-demo"])
        self.assertEqual(code, 0)
        self.assertEqual(len(json.loads(out)["satellites"]), 4)

    def test_missing_file_exits_2(self):
        code, _, err = self._run(["validate", "/nonexistent/scenario.json"])
        self.assertEqual(code, 2)
        self.assertIn('"path": "$"', err)

    def test_invalid_usage_exits_2(self):
        with self.assertRaises(SystemExit) as ctx, redirect_stderr(io.StringIO()):
            main([])
        self.assertEqual(ctx.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
