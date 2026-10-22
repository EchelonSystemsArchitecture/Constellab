"""Day 16: documented coordinate frames, Earth geometry and sun geometry.

Four frames matter to ConstellaLab, and every function names which one it takes
and returns instead of relying on a comment:

* **ECI** — non-rotating Earth-centred inertial, axes fixed at the scenario
  epoch. The contract carries positions and velocities here. +X is the vernal
  equinox direction (the standard ECI convention), so right ascension of the
  ascending node is measured from it and the solar position below is meaningful.
* **ECEF** — Earth-centred, Earth-fixed: the same origin and scale, rotated by
  the Earth rotation angle for the instant. Latitude/longitude live here.
* **Geodetic** — WGS-84 latitude, longitude and altitude above the ellipsoid.
  This is what a ground station or a map uses; the ellipsoid matters (a sphere
  is ~21 km wrong at the poles).
* **RSW** — radial / along-track / cross-track basis attached to a reference
  orbital state, used for relative geometry (sensor boresight, formation
  offsets). It is a rotation about the Earth centre, not a translation.

Angles are radians inside this module; the geodetic helpers take and return
degrees because latitude and longitude are always reported that way. Lengths are
kilometres, velocities kilometres per second, matching the contract. Use
``units.convert`` at any other boundary.

The Earth rotation rate is the real sidereal rate and the sun position is the
low-precision Astronomical Almanac formula (good to ~0.01°), which is enough for
eclipse seasons and illuminated-area geometry. Neither is a substitute for an
ephemeris: there is no nutation, precession, polar motion or penumbra.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any

Vector3 = tuple[float, float, float]

# --- Earth geometry -------------------------------------------------------------

MU_EARTH_KM3_S2 = 398600.4418

SECONDS_PER_EARTH_SIDEREAL_DAY = 86164.0905  # mean sidereal day, IAU/USNO convention
EARTH_ROTATION_RATE_RAD_S = 2.0 * math.pi / SECONDS_PER_EARTH_SIDEREAL_DAY
EARTH_EQUATORIAL_RADIUS_KM = 6378.137  # WGS-84 semi-major axis
WGS84_FLATTENING = 1.0 / 298.257223563
EARTH_POLAR_RADIUS_KM = EARTH_EQUATORIAL_RADIUS_KM * (1.0 - WGS84_FLATTENING)
WGS84_ECCENTRICITY_SQ = WGS84_FLATTENING * (2.0 - WGS84_FLATTENING)
# Mean obliquity of the ecliptic (IAU 2006), used by the solar model.
EARTH_AXIAL_TILT_DEG = 23.4392911

# Backwards-compatible alias: the contract's ECI uses the equatorial radius as
# the surface reference for "above Earth" checks and altitude readouts.
EARTH_RADIUS_KM = EARTH_EQUATORIAL_RADIUS_KM


def earth_rotation_angle_rad(time_s: float) -> float:
    """Earth rotation angle at ``time_s`` seconds since the scenario epoch.

    One full 360° turn takes a mean sidereal day, so a ground observer sweeps
    15.041° of ECI longitude per hour. The ECI frame itself does not rotate;
    this angle is the link between ECI and Earth-fixed coordinates.
    """
    return math.remainder((time_s / SECONDS_PER_EARTH_SIDEREAL_DAY) * 2.0 * math.pi, 2.0 * math.pi)


def rotate_z(vector: Vector3, angle_rad: float) -> Vector3:
    c, s = math.cos(angle_rad), math.sin(angle_rad)
    return (c * vector[0] - s * vector[1], s * vector[0] + c * vector[1], vector[2])


def _cross(a: Vector3, b: Vector3) -> Vector3:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _norm(v: Vector3) -> float:
    return math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])


def _unit(v: Vector3) -> Vector3:
    n = _norm(v)
    if n == 0.0:
        raise ValueError("zero vector has no direction")
    return (v[0] / n, v[1] / n, v[2] / n)


# --- frames ---------------------------------------------------------------------

class Frame(str, Enum):
    """Every frame this module can convert between."""

    ECI = "eci"
    ECEF = "ecef"
    GEODETIC = "geodetic"
    RSW = "rsw"


@dataclass(frozen=True)
class GeodeticPoint:
    """WGS-84 latitude/longitude in degrees and altitude above the ellipsoid."""

    latitude_deg: float
    longitude_deg: float
    altitude_km: float

    def to_ecef(self) -> Vector3:
        lat, lon = math.radians(self.latitude_deg), math.radians(self.longitude_deg)
        sin_lat, cos_lat = math.sin(lat), math.cos(lat)
        n = EARTH_EQUATORIAL_RADIUS_KM / math.sqrt(1.0 - WGS84_ECCENTRICITY_SQ * sin_lat * sin_lat)
        x = (n + self.altitude_km) * cos_lat * math.cos(lon)
        y = (n + self.altitude_km) * cos_lat * math.sin(lon)
        z = (n * (1.0 - WGS84_ECCENTRICITY_SQ) + self.altitude_km) * sin_lat
        return (x, y, z)

    def to_eci(self, time_s: float) -> Vector3:
        return rotate_z(self.to_ecef(), earth_rotation_angle_rad(time_s))


def ecef_from_geodetic(latitude_deg: float, longitude_deg: float, altitude_km: float) -> Vector3:
    return GeodeticPoint(latitude_deg, longitude_deg, altitude_km).to_ecef()


def geodetic_from_ecef(position_km: Vector3) -> GeodeticPoint:
    """Iterative WGS-84 ECEF -> geodetic conversion (Bowring-style fixed point)."""
    x, y, z = position_km
    lon = math.atan2(y, x)
    p = math.hypot(x, y)
    if p < 1e-9:
        # On the spin axis: longitude is undefined by geometry, so report 0 and
        # use the polar radius for altitude rather than dividing by cos(lat)=0.
        lat = math.pi / 2.0 if z >= 0 else -math.pi / 2.0
        return GeodeticPoint(math.degrees(lat), 0.0, abs(z) - EARTH_POLAR_RADIUS_KM)
    lat = math.atan2(z, p * (1.0 - WGS84_ECCENTRICITY_SQ))
    altitude = 0.0
    for _ in range(8):
        sin_lat = math.sin(lat)
        n = EARTH_EQUATORIAL_RADIUS_KM / math.sqrt(
            1.0 - WGS84_ECCENTRICITY_SQ * sin_lat * sin_lat
        )
        altitude = p / math.cos(lat) - n
        lat = math.atan2(z, p * (1.0 - WGS84_ECCENTRICITY_SQ * n / (n + altitude)))
    sin_lat = math.sin(lat)
    n = EARTH_EQUATORIAL_RADIUS_KM / math.sqrt(1.0 - WGS84_ECCENTRICITY_SQ * sin_lat * sin_lat)
    altitude = p / math.cos(lat) - n
    return GeodeticPoint(math.degrees(lat), math.degrees(lon), altitude)


def geodetic_from_eci(position_km: Vector3, time_s: float) -> GeodeticPoint:
    return geodetic_from_ecef(eci_to_ecef(position_km, 0.0, time_s))


def eci_to_ecef(position_km: Vector3, velocity_km_s: float | Vector3, time_s: float
                ) -> Vector3 | tuple[Vector3, Vector3]:
    """Rotate ECI into ECEF, subtracting Earth's spin from the velocity.

    Position rotates by -θ; velocity additionally loses ``ω × r`` because the
    frame itself is turning. Passing a scalar velocity (normally 0.0) returns
    just the rotated position, which is what ground-track code wants.
    """
    angle = earth_rotation_angle_rad(time_s)
    position = rotate_z(position_km, -angle)
    if isinstance(velocity_km_s, (int, float)):
        return position
    velocity = rotate_z(velocity_km_s, -angle)
    omega_r = (-EARTH_ROTATION_RATE_RAD_S * position[1],
               EARTH_ROTATION_RATE_RAD_S * position[0],
               0.0)
    return position, (velocity[0] - omega_r[0], velocity[1] - omega_r[1], velocity[2] - omega_r[2])


def ecef_to_eci(position_km: Vector3, velocity_km_s: Vector3 | None, time_s: float
                ) -> Vector3 | tuple[Vector3, Vector3]:
    angle = earth_rotation_angle_rad(time_s)
    position = rotate_z(position_km, angle)
    if velocity_km_s is None:
        return position
    velocity = rotate_z(velocity_km_s, angle)
    omega_r = (-EARTH_ROTATION_RATE_RAD_S * position[1],
               EARTH_ROTATION_RATE_RAD_S * position[0],
               0.0)
    return position, (velocity[0] + omega_r[0], velocity[1] + omega_r[1], velocity[2])


def rsw_basis(position_km: Vector3, velocity_km_s: Vector3) -> tuple[Vector3, Vector3, Vector3]:
    """Radial, along-track and cross-track unit vectors of an orbital state."""
    radial = _unit(position_km)
    cross = _cross(position_km, velocity_km_s)
    if _norm(cross) < 1e-12:
        raise ValueError("position and velocity are collinear: no orbital plane")
    cross_track = _unit(cross)
    along_track = _cross(cross_track, radial)
    return radial, along_track, cross_track


def eci_to_rsw(vector_eci: Vector3, position_km: Vector3, velocity_km_s: Vector3) -> Vector3:
    r, s, w = rsw_basis(position_km, velocity_km_s)
    return tuple(sum(component * axis for component, axis in zip(vector_eci, basis))
                 for basis in (r, s, w))  # type: ignore[return-value]


def rsw_to_eci(vector_rsw: Vector3, position_km: Vector3, velocity_km_s: Vector3) -> Vector3:
    r, s, w = rsw_basis(position_km, velocity_km_s)
    return tuple(vector_rsw[0] * r[i] + vector_rsw[1] * s[i] + vector_rsw[2] * w[i]
                 for i in range(3))  # type: ignore[return-value]


@dataclass(frozen=True)
class StateVector:
    """A position/velocity pair that remembers which frame it is expressed in."""

    frame: Frame
    position_km: Vector3
    velocity_km_s: Vector3

    def to(self, frame: Frame, *, time_s: float = 0.0) -> "StateVector":
        """Convert between inertial and Earth-fixed frames at ``time_s``."""
        if frame == self.frame:
            return self
        if (self.frame, frame) == (Frame.ECI, Frame.ECEF):
            position, velocity = eci_to_ecef(self.position_km, self.velocity_km_s, time_s)  # type: ignore[misc]
            return StateVector(Frame.ECEF, position, velocity)
        if (self.frame, frame) == (Frame.ECEF, Frame.ECI):
            position, velocity = ecef_to_eci(self.position_km, self.velocity_km_s, time_s)  # type: ignore[misc]
            return StateVector(Frame.ECI, position, velocity)
        raise ValueError(f"no direct transform from {self.frame.value} to {frame.value}")

    def geodetic(self, *, time_s: float = 0.0) -> GeodeticPoint:
        point = self if self.frame == Frame.ECEF else self.to(Frame.ECEF, time_s=time_s)
        return geodetic_from_ecef(point.position_km)

    def relative_to(self, reference: "StateVector") -> Vector3:
        """Offset from ``reference`` in its RSW basis, both states in ECI."""
        if self.frame != Frame.ECI or reference.frame != Frame.ECI:
            raise ValueError("relative geometry is defined in ECI")
        offset = tuple(a - b for a, b in zip(self.position_km, reference.position_km))
        return eci_to_rsw(offset, reference.position_km, reference.velocity_km_s)  # type: ignore[arg-type]

    def radius_km(self) -> float:
        return _norm(self.position_km)

    def speed_km_s(self) -> float:
        return _norm(self.velocity_km_s)


# --- sun and eclipse -------------------------------------------------------------

J2000_UNIX_S = 946_728_000.0  # 2000-01-01T12:00:00Z
SECONDS_PER_DAY = 86_400.0


def parse_utc(instant: str) -> datetime:
    """Parse the contract's ``...Z`` timestamps (also accepts explicit offsets)."""
    text = instant.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def days_since_j2000(epoch_utc: str, time_s: float = 0.0) -> float:
    epoch = parse_utc(epoch_utc)
    unix_s = epoch.timestamp() + time_s
    return (unix_s - J2000_UNIX_S) / SECONDS_PER_DAY


def sun_direction_eci(epoch_utc: str, time_s: float = 0.0) -> Vector3:
    """Unit vector from Earth towards the sun, in ECI.

    Low-precision Astronomical Almanac solar coordinates: mean longitude and
    mean anomaly advance at the mean rates, the equation of centre adds the two
    dominant periodic terms, and the ecliptic is tilted by the mean obliquity.
    No nutation, aberration, precession or ephemeris file is involved.
    """
    n = days_since_j2000(epoch_utc, time_s)
    mean_longitude_deg = 280.460 + 0.9856474 * n
    mean_anomaly_deg = 357.528 + 0.9856003 * n
    g = math.radians(mean_anomaly_deg)
    ecliptic_longitude = math.radians(
        mean_longitude_deg + 1.915 * math.sin(g) + 0.020 * math.sin(2.0 * g)
    )
    obliquity = math.radians(EARTH_AXIAL_TILT_DEG - 0.0000004 * n)
    return (
        math.cos(ecliptic_longitude),
        math.sin(ecliptic_longitude) * math.cos(obliquity),
        math.sin(ecliptic_longitude) * math.sin(obliquity),
    )


def sun_declination_deg(epoch_utc: str, time_s: float = 0.0) -> float:
    return math.degrees(math.asin(sun_direction_eci(epoch_utc, time_s)[2]))


def in_earth_shadow(position_km: Vector3, sun_unit_eci: Vector3,
                    earth_radius_km: float = EARTH_EQUATORIAL_RADIUS_KM) -> bool:
    """True inside Earth's cylindrical umbra (no penumbra, spherical Earth).

    A satellite is shadowed when it is on the anti-sun side of the planet and
    within one Earth radius of the shadow axis. This is the standard first-order
    eclipse model used for power budgets.
    """
    along = sum(p * s for p, s in zip(position_km, sun_unit_eci))
    if along >= 0.0:
        return False
    perpendicular = math.sqrt(max(0.0, _norm(position_km) ** 2 - along * along))
    return perpendicular < earth_radius_km


def sunlit_fraction(position_km: Vector3, sun_unit_eci: Vector3,
                    earth_radius_km: float = EARTH_EQUATORIAL_RADIUS_KM) -> float:
    """1.0 in sunlight, 0.0 in shadow — a number, so it can be summed."""
    return 0.0 if in_earth_shadow(position_km, sun_unit_eci, earth_radius_km) else 1.0


def frames_payload() -> dict[str, Any]:
    """Machine-readable frame descriptions for status/API output."""
    return {
        "frames": {
            Frame.ECI.value: "non-rotating Earth-centred inertial, axes fixed at epoch; +X is the vernal equinox",
            Frame.ECEF.value: "Earth-centred Earth-fixed, rotated by earth_rotation_angle_rad(time_s)",
            Frame.GEODETIC.value: "WGS-84 latitude/longitude (deg) and altitude above the ellipsoid (km)",
            Frame.RSW.value: "radial / along-track / cross-track basis of a reference orbital state",
        },
        "earth": {
            "equatorial_radius_km": EARTH_EQUATORIAL_RADIUS_KM,
            "polar_radius_km": EARTH_POLAR_RADIUS_KM,
            "flattening": WGS84_FLATTENING,
            "sidereal_day_s": SECONDS_PER_EARTH_SIDEREAL_DAY,
            "rotation_rate_rad_s": EARTH_ROTATION_RATE_RAD_S,
        },
        "sun": {
            "model": "low-precision Astronomical Almanac solar coordinates",
            "mean_obliquity_deg": EARTH_AXIAL_TILT_DEG,
            "shadow": "cylindrical umbra, spherical Earth, no penumbra",
        },
    }
