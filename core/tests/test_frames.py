"""Day 16 acceptance: documented coordinate frames, Earth and sun geometry.

The renderer only sees ECI positions, but ground tracks, sun factors and the
parameter registry all live in these conversions. Pinned here:

* WGS-84 geodetic <-> ECEF round-trips to centimetre precision,
* ECI <-> ECEF rotate by exactly the Earth's sidereal rotation angle,
* the RSW basis is orthonormal and inverts,
* sun direction / declination / cylindrical shadow behave like the almanac.
"""

from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from constellab_core.frames import (  # noqa: E402
    EARTH_AXIAL_TILT_DEG,
    EARTH_EQUATORIAL_RADIUS_KM,
    EARTH_POLAR_RADIUS_KM,
    SECONDS_PER_EARTH_SIDEREAL_DAY,
    WGS84_FLATTENING,
    Frame,
    GeodeticPoint,
    StateVector,
    earth_rotation_angle_rad,
    ecef_from_geodetic,
    eci_to_ecef,
    eci_to_rsw,
    ecef_to_eci,
    geodetic_from_ecef,
    geodetic_from_eci,
    in_earth_shadow,
    frames_payload,
    rsw_basis,
    rsw_to_eci,
    sun_declination_deg,
    sun_direction_eci,
    sunlit_fraction,
)


def norm(v):
    return math.sqrt(sum(c * c for c in v))


class TestEarthGeometry(unittest.TestCase):
    def test_wgs84_constants_match_the_reference_ellipsoid(self):
        self.assertEqual(EARTH_EQUATORIAL_RADIUS_KM, 6378.137)
        self.assertAlmostEqual(WGS84_FLATTENING, 1.0 / 298.257223563, places=15)
        self.assertAlmostEqual(
            EARTH_POLAR_RADIUS_KM, EARTH_EQUATORIAL_RADIUS_KM * (1.0 - WGS84_FLATTENING), places=9
        )

    def test_geodetic_ecef_round_trip_is_centimetre_accurate(self):
        points = (
            (0.0, 0.0, 0.0),
            (0.0, 90.0, 400.0),
            (51.4992, -0.1275, 0.0),
            (-33.8674, 151.2071, 550.0),
            (89.9, 12.0, 1200.0),
        )
        for lat, lon, alt in points:
            with self.subTest(lat=lat, lon=lon, alt=alt):
                ecef = ecef_from_geodetic(lat, lon, alt)
                back = geodetic_from_ecef(ecef)
                self.assertAlmostEqual(back.latitude_deg, lat, places=6)
                self.assertAlmostEqual(back.longitude_deg, lon, places=6)
                self.assertAlmostEqual(back.altitude_km, alt, places=6)

    def test_sea_level_geodetic_radius_is_the_ellipsoid(self):
        # A point at 0/0 on the ellipsoid sits at the equatorial radius.
        ecef = ecef_from_geodetic(0.0, 0.0, 0.0)
        self.assertAlmostEqual(norm(ecef), EARTH_EQUATORIAL_RADIUS_KM, places=6)


class TestEarthRotation(unittest.TestCase):
    def test_rotation_uses_the_mean_sidereal_day(self):
        self.assertEqual(SECONDS_PER_EARTH_SIDEREAL_DAY, 86164.0905)
        # 360° per sidereal day = 15.041°/h, exact to the documented precision.
        self.assertAlmostEqual(
            math.degrees(earth_rotation_angle_rad(3600.0)), 15.0411, places=3
        )

    def test_rotation_wraps_to_a_full_turn(self):
        self.assertAlmostEqual(
            earth_rotation_angle_rad(SECONDS_PER_EARTH_SIDEREAL_DAY * 7), 0.0, places=9
        )
        half = math.degrees(earth_rotation_angle_rad(SECONDS_PER_EARTH_SIDEREAL_DAY / 2.0))
        self.assertAlmostEqual(half, 180.0, places=9)


class TestFrameConversions(unittest.TestCase):
    EPOCH_SECONDS = 43200.0  # half a day in, so theta is neither 0 nor 180 deg

    def test_eci_ecef_round_trip_recovers_the_state(self):
        position = (7000.0, 1200.0, -800.0)
        velocity = (1.1, 6.9, 2.2)
        ecef_position, ecef_velocity = eci_to_ecef(position, velocity, self.EPOCH_SECONDS)
        back_position, back_velocity = ecef_to_eci(ecef_position, ecef_velocity, self.EPOCH_SECONDS)
        for i in range(3):
            with self.subTest(axis=i):
                self.assertAlmostEqual(back_position[i], position[i], places=9)
                self.assertAlmostEqual(back_velocity[i], velocity[i], places=9)

    def test_eci_to_ecef_preserves_speed_and_loses_spin_from_velocity(self):
        # A satellite parked 1 km above the equator in ECEF-frame terms: in ECI
        # its velocity carries the Earth's spin at radius r.
        position = (EARTH_EQUATORIAL_RADIUS_KM + 1.0, 0.0, 0.0)
        spin_rate_km_s = (2.0 * math.pi / SECONDS_PER_EARTH_SIDEREAL_DAY) * position[0]
        _, ecef_velocity = eci_to_ecef(position, (0.0, spin_rate_km_s, 0.0), 0.0)
        self.assertAlmostEqual(ecef_velocity[1], 0.0, places=6)  # matches the ground
        for i in range(3):
            self.assertAlmostEqual(ecef_velocity[i], 0.0, places=6)

    def test_geodetic_from_eci_follows_the_rotating_ground(self):
        # The Greenwich-equator ECEF point stays at lon 0 in ECEF at any time;
        # in ECI it rotates at exactly the Earth's rate.
        for time_s in (0.0, 3600.0, SECONDS_PER_EARTH_SIDEREAL_DAY * 0.25):
            with self.subTest(time_s=time_s):
                point = geodetic_from_eci(
                    ecef_to_eci(ecef_from_geodetic(0.0, 0.0, 0.0), None, time_s),  # type: ignore[arg-type]
                    time_s,
                )
                self.assertAlmostEqual(point.latitude_deg, 0.0, places=6)
                self.assertAlmostEqual(point.longitude_deg, 0.0, places=6)

    def test_polar_axis_geodetic_falls_back_gracefully(self):
        point = geodetic_from_ecef((0.0, 0.0, EARTH_POLAR_RADIUS_KM))
        self.assertAlmostEqual(point.latitude_deg, 90.0, places=6)
        self.assertAlmostEqual(point.altitude_km, 0.0, places=6)

    def test_state_vector_only_converts_between_inertial_pairs(self):
        state = StateVector(Frame.ECI, (7000.0, 0.0, 0.0), (0.0, 7.5, 0.0))
        ecef = state.to(Frame.ECEF, time_s=self.EPOCH_SECONDS)
        self.assertEqual(ecef.frame, Frame.ECEF)
        back = ecef.to(Frame.ECI, time_s=self.EPOCH_SECONDS)
        self.assertAlmostEqual(back.position_km[0], state.position_km[0], places=9)
        self.assertEqual(state.to(Frame.ECI), state)  # identity conversion
        with self.assertRaises(ValueError):
            ecef.to(Frame.GEODETIC)


class TestRswFrame(unittest.TestCase):
    def test_basis_is_orthonormal_and_right_handed(self):
        position = (7000.0, 100.0, -300.0)
        velocity = (-1.0, 7.0, 0.4)
        radial, along, cross = rsw_basis(position, velocity)
        for basis, name in ((radial, "r"), (along, "s"), (cross, "w")):
            with self.subTest(axis=name):
                self.assertAlmostEqual(norm(basis), 1.0, places=12)
        for first, second in ((radial, along), (radial, cross), (along, cross)):
            self.assertAlmostEqual(
                sum(a * b for a, b in zip(first, second)), 0.0, places=12
            )

    def test_rsw_round_trip_preserves_the_vector(self):
        position = (6524.834, 6862.875, 6448.296)
        velocity = (4.901327, 5.533756, -1.976341)
        vector = (12.3, -4.5, 678.9)
        back = rsw_to_eci(eci_to_rsw(vector, position, velocity), position, velocity)
        for i in range(3):
            with self.subTest(axis=i):
                self.assertAlmostEqual(back[i], vector[i], places=9)

    def test_collinear_state_has_no_orbital_plane(self):
        with self.assertRaises(ValueError):
            rsw_basis((1.0, 2.0, 3.0), (2.0, 4.0, 6.0))


class TestSunGeometry(unittest.TestCase):
    def test_sun_direction_is_a_unit_vector(self):
        sun = sun_direction_eci("2026-10-12T00:00:00Z", 0.0)
        self.assertAlmostEqual(norm(sun), 1.0, places=12)

    def test_declination_stays_inside_the_tropics(self):
        for day in range(0, 366, 7):
            sun = sun_declination_deg("2026-01-01T00:00:00Z", day * 86400.0)
            with self.subTest(day=day):
                self.assertLess(sun, EARTH_AXIAL_TILT_DEG + 1.0)
                self.assertGreater(sun, -EARTH_AXIAL_TILT_DEG - 1.0)

    def test_equinox_declination_is_nearly_zero(self):
        sun = sun_declination_deg("2026-03-20T12:00:00Z", 0.0)
        self.assertLess(abs(sun), 1.5)

    def test_umbra_geometry(self):
        sun = sun_direction_eci("2026-10-12T00:00:00Z", 0.0)
        radius = EARTH_EQUATORIAL_RADIUS_KM
        # Orthonormal basis along / across the shadow axis at this epoch.
        axis = tuple(c / norm(sun) for c in sun)
        seed = (0.0, 0.0, 1.0) if abs(axis[2]) < 0.9 else (1.0, 0.0, 0.0)
        perp = tuple(a - b for a, b in zip(seed, (sum(a * b for a, b in zip(seed, axis)),) * 3))
        perp = tuple(c / norm(perp) for c in perp)

        def shadow_point(along_km, across_km):
            return tuple(
                along_km * axis[i] + across_km * perp[i] for i in range(3)
            )

        # Anti-sun side, well inside the shadow cylinder.
        self.assertTrue(in_earth_shadow(shadow_point(-radius, 10.0), sun))
        self.assertEqual(sunlit_fraction(shadow_point(-radius, 10.0), sun), 0.0)
        # Anti-sun side but far off-axis: in sunlight.
        self.assertFalse(in_earth_shadow(shadow_point(-radius, 10.0 * radius), sun))
        # Sun-side is never shadowed, whatever the offset.
        self.assertFalse(in_earth_shadow(shadow_point(radius, 0.0), sun))
        self.assertEqual(sunlit_fraction(shadow_point(2.0 * radius, 0.0), sun), 1.0)

    def test_frames_payload_documents_every_frame(self):
        payload = frames_payload()
        for frame in Frame:
            self.assertIn(frame.value, payload["frames"])
        self.assertIn("sidereal_day_s", payload["earth"])
        self.assertIn("model", payload["sun"])


if __name__ == "__main__":
    unittest.main()
