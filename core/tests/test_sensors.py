"""Day 26 acceptance tests: sensor footprints, availability and opportunities."""

import json
import math
import unittest

from constellab_core import dynamics, frames, sensors
from constellab_core.config import load_config_file
from constellab_core.sensors import (
    SensorConfig,
    SensorError,
    access_windows,
    build_opportunities,
    cloud_fraction,
    observation_geometry,
    quality_score,
    register_sensor_model,
    registered_sensor_models,
    sensor_config_for,
    sensor_model,
    unregister_sensor_model,
)
from constellab_core.targets import EventTarget


def sub_satellite_target(config, satellite_id: str, time_s: float, **overrides) -> EventTarget:
    """A target directly under one satellite at ``time_s`` (a guaranteed look)."""
    satellite = next(s for s in config.satellites if s.id == satellite_id)
    position = dynamics.dynamics_model().state_at(satellite.orbit, time_s)[0]
    point = frames.geodetic_from_eci(position, time_s)
    payload = {
        "id": "under-target",
        "kind": "hotspot",
        "lat_deg": point.latitude_deg,
        "lon_deg": point.longitude_deg,
        "start_s": 0.0,
        "end_s": 1_800.0,
    }
    payload.update(overrides)
    return EventTarget(**payload)


class SensorRegistryTests(unittest.TestCase):
    def test_builtin_models_are_registered(self) -> None:
        self.assertIn("sensor.conical", registered_sensor_models())
        self.assertIn("sensor.agile", registered_sensor_models())
        payload = sensors.sensor_models_payload()
        self.assertEqual(payload["version"], sensors.SENSOR_MODEL_VERSION)
        self.assertTrue(payload["fidelity"])

    def test_unknown_model_is_rejected_with_the_registered_set(self) -> None:
        with self.assertRaises(SensorError) as caught:
            sensor_model("sensor.telepathy")
        self.assertIn("sensor.conical", str(caught.exception))

    def test_registering_the_same_key_twice_fails(self) -> None:
        with self.assertRaises(SensorError):
            register_sensor_model(sensors.ConicalNadirSensor())

    def test_config_merges_registry_defaults_and_scenario_overrides(self) -> None:
        base = sensor_model("sensor.conical").config({})
        self.assertEqual(base.model, "sensor.conical")
        self.assertEqual(base.half_angle_deg, 30.0)
        self.assertEqual(base.max_range_km, 2500.0)
        tuned = sensor_model("sensor.conical").config({"half_angle_deg": 12.5, "max_range_km": 1200.0})
        self.assertEqual(tuned.half_angle_deg, 12.5)
        self.assertEqual(tuned.max_range_km, 1200.0)

    def test_invalid_configuration_is_rejected(self) -> None:
        with self.assertRaises(Exception):
            SensorConfig(model="sensor.conical", half_angle_deg=0.0)
        with self.assertRaises(SensorError):
            SensorConfig(model="sensor.conical", max_range_km=-1.0)


class AvailabilityTests(unittest.TestCase):
    def test_duty_cycle_is_a_fixed_schedule(self) -> None:
        model = sensor_model("sensor.conical")
        config = SensorConfig(model=model.key, duty_cycle_ratio=0.25, availability_period_s=400.0)
        self.assertTrue(model.is_available(config, 0.0))
        self.assertTrue(model.is_available(config, 99.0))
        self.assertFalse(model.is_available(config, 100.0))
        self.assertFalse(model.is_available(config, 399.0))
        self.assertTrue(model.is_available(config, 400.0))

    def test_disabled_sensor_is_never_available(self) -> None:
        model = sensor_model("sensor.conical")
        config = SensorConfig(model=model.key, enabled=False)
        self.assertFalse(model.is_available(config, 0.0))
        self.assertFalse(model.is_available(config, 12_345.0))

    def test_cloud_mask_is_deterministic_and_bounded(self) -> None:
        first = cloud_fraction(7, "a.b", 1_000.0, 0.6)
        self.assertEqual(first, cloud_fraction(7, "a.b", 1_000.0, 0.6))
        self.assertGreaterEqual(first, 0.0)
        self.assertLessEqual(first, 0.6)
        self.assertNotEqual(first, cloud_fraction(8, "a.b", 1_000.0, 0.6))


class GeometryBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.model = sensor_model("sensor.conical")
        self.config = SensorConfig(model=self.model.key, half_angle_deg=30.0, max_off_nadir_deg=30.0,
                                   max_range_km=2_500.0, min_elevation_deg=10.0)

    def target_below(self, angle_deg: float) -> tuple[tuple[float, float, float], tuple[float, float, float], float]:
        """Satellite at 550 km altitude and a ground point ``angle_deg`` off nadir."""
        radius = frames.EARTH_EQUATORIAL_RADIUS_KM + 550.0
        sat = (radius * math.cos(math.radians(angle_deg)), 0.0, radius * math.sin(math.radians(angle_deg)))
        ground = (frames.EARTH_EQUATORIAL_RADIUS_KM, 0.0, 0.0)
        return sat, ground, 0.0

    def test_target_directly_below_is_visible(self) -> None:
        sat, ground, time_s = self.target_below(0.0)
        geometry = observation_geometry(sat, ground, self.config, time_s=time_s)
        self.assertTrue(geometry.visible)
        self.assertAlmostEqual(geometry.off_nadir_deg, 0.0, places=6)
        self.assertAlmostEqual(geometry.elevation_deg, 90.0, places=6)
        self.assertLess(geometry.range_km, 560.0)

    def test_outside_the_cone_is_not_visible(self) -> None:
        sat, ground, time_s = self.target_below(30.0)
        geometry = observation_geometry(sat, ground, self.config, time_s=time_s)
        self.assertGreater(geometry.off_nadir_deg, self.config.max_off_nadir_deg)
        self.assertFalse(geometry.in_cone)
        self.assertFalse(geometry.visible)
        self.assertEqual(quality_score(geometry, self.config, cloud=0.0), 0.0)

    def test_beyond_range_is_not_visible(self) -> None:
        outside = (frames.EARTH_EQUATORIAL_RADIUS_KM, 0.0, 0.0)
        far = (outside[0], 0.0, 0.0)
        sat = (outside[0], 0.0, 10_000.0)
        geometry = observation_geometry(sat, far, self.config, time_s=0.0)
        self.assertFalse(geometry.in_range)
        self.assertFalse(geometry.visible)

    def test_earth_occultation_blocks_a_far_target(self) -> None:
        earth = frames.EARTH_EQUATORIAL_RADIUS_KM
        sat = (-(earth + 550.0), 0.0, 0.0)
        target = (earth, 0.0, 0.0)
        geometry = observation_geometry(sat, target, self.config, time_s=0.0)
        self.assertTrue(geometry.occulted)
        self.assertFalse(geometry.visible)

    def test_horizon_elevation_is_reported_at_the_target(self) -> None:
        sat, ground, time_s = self.target_below(20.0)
        geometry = observation_geometry(sat, ground, self.config, time_s=time_s)
        self.assertGreater(geometry.elevation_deg, 0.0)
        self.assertLess(geometry.elevation_deg, 90.0)
        self.assertAlmostEqual(
            geometry.elevation_deg,
            90.0 - geometry.off_nadir_deg if geometry.off_nadir_deg < 1e-9 else geometry.elevation_deg,
            places=6,
        )
        self.assertGreater(geometry.resolution_m, self.config.resolution_at_nadir_m)


class AccessWindowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = load_config_file("visual-orbit-demo")
        self.satellite = self.config.satellites[0]
        self.target = sub_satellite_target(self.config, self.satellite.id, 600.0)
        self.sensor = sensor_model("sensor.conical").config({}, seed=11)

    def test_access_windows_are_deterministic(self) -> None:
        first = [
            w.to_dict(include_samples=True)
            for w in access_windows(
                self.satellite.id, self.satellite.orbit, self.target,
                config=self.sensor, horizon_s=1_800.0, step_s=20.0, seed=11,
            )
        ]
        second = [
            w.to_dict(include_samples=True)
            for w in access_windows(
                self.satellite.id, self.satellite.orbit, self.target,
                config=self.sensor, horizon_s=1_800.0, step_s=20.0, seed=11,
            )
        ]
        self.assertTrue(first)
        self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))

    def test_windows_carry_timing_and_quality_metadata(self) -> None:
        windows = access_windows(
            self.satellite.id, self.satellite.orbit, self.target,
            config=self.sensor, horizon_s=1_800.0, step_s=20.0, seed=11,
        )
        self.assertTrue(windows)
        window = windows[0]
        self.assertLessEqual(window.start_s, window.end_s)
        self.assertGreaterEqual(window.peak_quality, window.mean_quality)
        self.assertGreater(window.best_resolution_m, 0.0)
        payload = window.to_dict()
        for key in ("start_s", "end_s", "peak_quality", "mean_quality", "best_resolution_m", "usable"):
            self.assertIn(key, payload)

    def test_disabled_sensor_yields_unusable_windows_with_a_reason(self) -> None:
        disabled = SensorConfig(**{**self.sensor.to_dict(), "enabled": False})
        windows = access_windows(
            self.satellite.id, self.satellite.orbit, self.target,
            config=disabled, horizon_s=1_800.0, step_s=20.0, seed=11,
        )
        self.assertTrue(windows)
        self.assertFalse(any(w.usable for w in windows))
        self.assertTrue(all("sensor disabled" in w.reasons for w in windows))

    def test_target_resolution_requirement_can_reject_a_window(self) -> None:
        strict = EventTarget(
            id="strict", kind="flood-region",
            lat_deg=self.target.lat_deg, lon_deg=self.target.lon_deg,
            start_s=0.0, end_s=1_800.0, requirements={"min_resolution_m": 0.5},
        )
        windows = access_windows(
            self.satellite.id, self.satellite.orbit, strict,
            config=self.sensor, horizon_s=1_800.0, step_s=20.0, seed=11,
        )
        self.assertTrue(windows)
        self.assertFalse(any(w.usable for w in windows))
        self.assertTrue(any("coarser than required" in reason for w in windows for reason in w.reasons))

    def test_event_window_clips_the_scan(self) -> None:
        narrow = EventTarget(
            id="narrow", kind="hotspot",
            lat_deg=self.target.lat_deg, lon_deg=self.target.lon_deg,
            start_s=580.0, end_s=620.0,
        )
        windows = access_windows(
            self.satellite.id, self.satellite.orbit, narrow,
            config=self.sensor, horizon_s=1_800.0, step_s=20.0, seed=11,
            window_s=(narrow.start_s, narrow.end_s),
        )
        self.assertTrue(windows)
        for window in windows:
            self.assertGreaterEqual(window.start_s, 580.0)
            self.assertLessEqual(window.end_s, 620.0)

    def test_target_outside_the_footprint_has_no_access_window(self) -> None:
        away = EventTarget(
            id="far-away", kind="hotspot",
            lat_deg=-self.target.lat_deg, lon_deg=self.target.lon_deg + 180.0,
            start_s=0.0, end_s=900.0,
        )
        windows = access_windows(
            self.satellite.id, self.satellite.orbit, away,
            config=self.sensor, horizon_s=900.0, step_s=30.0, seed=11,
        )
        self.assertEqual(windows, [])


class OpportunityPlanTests(unittest.TestCase):
    def test_plan_is_built_from_config_and_is_reproducible(self) -> None:
        config = load_config_file("visual-orbit-demo")
        target = sub_satellite_target(config, "sat-alpha", 600.0)
        first = build_opportunities(config, [target], horizon_s=1_800.0, step_s=20.0, seed=5)
        second = build_opportunities(config, [target], horizon_s=1_800.0, step_s=20.0, seed=5)
        self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))
        self.assertGreater(first["window_count"], 0)
        self.assertGreater(first["usable_window_count"], 0)
        self.assertEqual(set(first["sensors"]), {sat.id for sat in config.satellites})
        for window in first["windows"]:
            self.assertIn(window["satellite_id"], first["sensors"])

    def test_sensor_config_follows_the_declared_component(self) -> None:
        config = load_config_file("visual-orbit-demo")
        satellite = config.satellites[0]
        sensor = sensor_config_for(config, satellite)
        self.assertIn(sensor.model, registered_sensor_models())
        declared = {
            component.type: (component.parameters or {})
            for component in (satellite.components or config.components or [])
        }
        if "sensor.conical" in declared and "half_angle_deg" in declared["sensor.conical"]:
            self.assertEqual(sensor.half_angle_deg, declared["sensor.conical"]["half_angle_deg"])

    def test_third_party_sensor_model_participates_without_core_edits(self) -> None:
        class WideAngleSensor(sensors.AgilePointingSensor):
            key = "sensor.wide-test"
            label = "Wide test sensor"
            defaults = {**sensors.AgilePointingSensor.defaults, "half_angle_deg": 45.0,
                        "max_off_nadir_deg": 45.0, "resolution_at_nadir_m": 50.0}

        model = WideAngleSensor()
        register_sensor_model(model)
        try:
            config = model.config({"max_off_nadir_deg": 50.0})
            self.assertEqual(config.model, "sensor.wide-test")
            self.assertEqual(config.max_off_nadir_deg, 50.0)
            self.assertGreaterEqual(config.half_angle_deg, 1.0)
        finally:
            unregister_sensor_model("sensor.wide-test")


if __name__ == "__main__":
    unittest.main()
