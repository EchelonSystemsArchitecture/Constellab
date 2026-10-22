"""Day 16 acceptance: the single unit registry behind every numeric field.

Pinned promises, all from the field keys the rest of the core already uses:

* units live in canonical families and convert inside a family only,
* slug / key naming ties a field name to its unit (``battery_charge_j``,
  ``footprint_radius_km``) so the parameter registry can self-check,
* round-trips through the canonical unit reproduce the input value.
"""

from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from constellab_core.units import (  # noqa: E402
    UnitError,
    canonical_unit,
    convert,
    format_quantity,
    from_canonical,
    key_matches_unit,
    normalize_unit,
    Quantity,
    registry_payload,
    to_canonical,
    unit_kind,
    unit_slug,
    units_for,
)


class TestUnitsRegistry(unittest.TestCase):
    def test_registry_payload_is_complete_and_json_safe(self):
        payload = registry_payload()
        self.assertIn("canonical", payload)
        self.assertIn("units", payload)
        # Every listed unit maps back to a declared kind, with a slug for keys.
        for symbol, info in payload["units"].items():
            with self.subTest(symbol=symbol):
                self.assertIn(info["kind"], payload["canonical"])
                self.assertIsInstance(info["aliases"], list)
                self.assertEqual(info["slug"], unit_slug(symbol))

    def test_every_kind_has_a_canonical_unit(self):
        for kind, expected in (
            ("length", "m"), ("time", "s"), ("angle", "rad"), ("velocity", "m/s"),
            ("mass", "kg"), ("area", "m2"), ("power", "W"), ("energy", "J"),
            ("data", "bit"), ("data_rate", "bit/s"), ("frequency", "Hz"), ("ratio", "1"),
        ):
            self.assertEqual(canonical_unit(kind), expected, kind)
            self.assertGreater(len(units_for(kind)), 0, kind)

    def test_unknown_unit_is_an_error_not_a_default(self):
        with self.assertRaises(UnitError):
            normalize_unit("furlongs")
        with self.assertRaises(UnitError):
            unit_kind("furlongs")
        with self.assertRaises(UnitError):
            canonical_unit("loudness")


class TestUnitKinds(unittest.TestCase):
    def test_kinds_cover_the_registry_fields(self):
        self.assertEqual(unit_kind("m2"), "area")
        self.assertEqual(unit_kind("km"), "length")
        self.assertEqual(unit_kind("km/s"), "velocity")
        self.assertEqual(unit_kind("deg"), "angle")
        self.assertEqual(unit_kind("s"), "time")
        self.assertEqual(unit_kind("Hz"), "frequency")
        self.assertEqual(unit_kind("W"), "power")
        self.assertEqual(unit_kind("J"), "energy")
        self.assertEqual(unit_kind("bit/s"), "data_rate")
        self.assertEqual(unit_kind("1"), "ratio")

    def test_aliases_normalize_case_insensitively(self):
        self.assertEqual(normalize_unit("KM"), "km")
        self.assertEqual(normalize_unit("seconds"), "s")
        self.assertEqual(normalize_unit("Mbps"), "Mbit/s")
        self.assertEqual(normalize_unit("°"), "deg")
        with self.assertRaises(UnitError):
            normalize_unit(True)

    def test_conversions_inside_a_family_and_back(self):
        cases = (
            (1500.0, "m", "km", 1.5),
            (5400.0, "s", "h", 1.5),
            (2.0, "h", "min", 120.0),
            (180.0, "deg", "rad", math.pi),
            (1024.0, "kbit", "bit", 1024000.0),
            (400.0, "bit/s", "kbit/s", 0.4),
            (55.0, "%", "1", 0.55),
        )
        for value, source, target, expected in cases:
            with self.subTest(source=source, target=target):
                self.assertEqual(convert(value, source, target), expected)
                self.assertAlmostEqual(from_canonical(to_canonical(value, source), source), value, places=9)

    def test_canonical_round_trip_is_lossless_for_plain_values(self):
        for value, unit in ((7000.0, "km"), (0.29, "deg"), (3600.0, "s"), (91.6, "W")):
            with self.subTest(unit=unit):
                self.assertAlmostEqual(
                    from_canonical(to_canonical(value, unit), unit), value, places=12
                )

    def test_cross_family_conversion_is_rejected(self):
        with self.assertRaises(UnitError):
            convert(1.0, "m", "s")
        with self.assertRaises(UnitError):
            convert(1.0, "km", "bit")
        with self.assertRaises(UnitError):
            convert(float("nan"), "km", "m")


class TestKeySlugContract(unittest.TestCase):
    def test_keys_used_by_the_core_match_their_units(self):
        pairs = (
            ("semi_major_axis_km", "km"),
            ("inclination_deg", "deg"),
            ("raan_deg", "deg"),
            ("argument_of_perigee_deg", "deg"),
            ("true_anomaly_deg", "deg"),
            ("battery_charge_j", "J"),
            ("battery_capacity_j", "J"),
            ("footprint_radius_km", "km"),
            ("array_area_m2", "m2"),
            ("data_rate_bit_s", "bit/s"),
            ("task_duration_s", "s"),
            ("throughput_hz", "Hz"),
            ("supply_w", "W"),
            ("duty_cycle_ratio", "1"),
        )
        for key, unit in pairs:
            with self.subTest(key=key):
                self.assertTrue(key_matches_unit(key, unit), key)

    def test_ratio_keys_use_the_ratio_slug(self):
        self.assertEqual(unit_slug("1"), "ratio")
        self.assertEqual(unit_slug("%"), "pct")

    def test_mismatched_key_and_unit_fail(self):
        self.assertFalse(key_matches_unit("semi_major_axis_km", "s"))
        self.assertFalse(key_matches_unit("battery_charge_j", "W"))
        self.assertFalse(key_matches_unit("tasks", "J"))

    def test_slug_of_every_registered_unit_is_stable(self):
        for unit in ("km", "m2", "deg", "s", "Hz", "W", "J", "bit", "bit/s", "1"):
            self.assertEqual(unit_slug(unit), unit_slug(normalize_unit(unit)), unit)


class TestQuantity(unittest.TestCase):
    def test_quantity_converts_and_compares_through_its_canonical(self):
        q = Quantity(7.0, "km")
        self.assertEqual(q.kind, "length")
        self.assertAlmostEqual(q.canonical, 7000.0, places=9)
        self.assertEqual(q.to("m"), Quantity(7000.0, "m"))
        # Equal canonical values compare equal across spellings of the unit.
        self.assertEqual(q, Quantity(7000.0, "m"))

    def test_quantity_formatting_is_deterministic(self):
        self.assertEqual(format_quantity(1234.5678, "km", digits=2), "1,234.57 km")
        self.assertEqual(format_quantity(0.5, "1"), "0.500")
        self.assertEqual(str(Quantity(3.0, "deg")), "3.000 deg")

    def test_invalid_quantity_construction_fails_eagerly(self):
        with self.assertRaises(UnitError):
            Quantity(1.0, "furlongs")
        with self.assertRaises(UnitError):
            Quantity(float("nan"), "km")
        with self.assertRaises(UnitError):
            Quantity("7000", "km")

    def test_quantities_add_only_when_the_unit_kind_matches(self):
        total = Quantity(1.0, "km") + Quantity(500.0, "m")
        self.assertEqual(total, Quantity(1.5, "km"))
        with self.assertRaises(UnitError):
            Quantity(1.0, "km") + Quantity(1.0, "s")


if __name__ == "__main__":
    unittest.main()
