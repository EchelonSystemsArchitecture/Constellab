"""Smoke tests for the constellab_core package (Day 1 baseline)."""

from __future__ import annotations

import io
import json
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

sys.path.insert(0, r"C:\Users\bijan\Desktop\Projects\Tessera\core")

import constellab_core  # noqa: E402
from constellab_core import SCHEMA_VERSION, __version__  # noqa: E402
from constellab_core.__main__ import main  # noqa: E402
from constellab_core.config import ConfigError, validate_config  # noqa: E402
from constellab_core.service import status_payload  # noqa: E402


class TestPackage(unittest.TestCase):
    def test_package_imports(self):
        self.assertTrue(hasattr(constellab_core, "__version__"))
        self.assertIsInstance(SCHEMA_VERSION, int)

    def test_status_payload_shape(self):
        payload = status_payload()
        self.assertEqual(payload["name"], "constellab-core")
        self.assertEqual(payload["version"], __version__)
        self.assertEqual(payload["schema_version"], SCHEMA_VERSION)
        self.assertEqual(payload["status"], "ok")
        self.assertIn("endpoints", payload)
        self.assertIn("GET /api/status", payload["endpoints"])


class TestConfigValidation(unittest.TestCase):
    def test_defaults(self):
        effective = validate_config({})
        self.assertEqual(effective["satellites"], 4)
        self.assertEqual(effective["seed"], 0)

    def test_valid_full(self):
        effective = validate_config({"name": "demo", "satellites": 8, "seed": 42})
        self.assertEqual(effective, {"name": "demo", "satellites": 8, "seed": 42})

    def test_unknown_field_rejected(self):
        with self.assertRaises(ConfigError) as ctx:
            validate_config({"telemetry_rate_hz": 10})
        self.assertEqual(ctx.exception.errors[0]["path"], "$.telemetry_rate_hz")

    def test_out_of_range_rejected(self):
        with self.assertRaises(ConfigError) as ctx:
            validate_config({"satellites": 0})
        self.assertEqual(ctx.exception.errors[0]["path"], "$.satellites")

    def test_non_object_rejected(self):
        with self.assertRaises(ConfigError):
            validate_config([1, 2, 3])


class TestCli(unittest.TestCase):
    def _run(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_status_command(self):
        code, out, _ = self._run(["status"])
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["status"], "ok")

    def test_status_with_valid_config(self):
        import tempfile, os
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            json.dump({"name": "demo", "satellites": 4}, fh)
            path = fh.name
        try:
            code, out, _ = self._run(["status", "--config", path])
            self.assertEqual(code, 0)
        finally:
            os.unlink(path)

    def test_status_with_invalid_config_exits_2(self):
        import tempfile, os
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            json.dump({"satellites": -1}, fh)
            path = fh.name
        try:
            code, _, err = self._run(["status", "--config", path])
            self.assertEqual(code, 2)
            self.assertIn("$.satellites", err)
        finally:
            os.unlink(path)

    def test_invalid_usage_exits_3(self):
        with mock.patch.object(sys, "argv", ["constellab_core"]):
            parser_error = False
            try:
                main([])
            except SystemExit as exc:
                parser_error = exc.code == 2
            self.assertTrue(parser_error)


if __name__ == "__main__":
    unittest.main()
