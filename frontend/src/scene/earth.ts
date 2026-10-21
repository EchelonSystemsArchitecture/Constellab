import type { Vector3Km } from "../contract";
import { SCENE_CONFIG } from "./config";

/**
 * Real-world Earth orientation helpers.
 *
 * The contract's frame is Earth-centred inertial (ECI) and fixed at the epoch,
 * so the planet itself does not move in it: everything that ties the simulation
 * to the ground (globe spin, sub-satellite longitude, solar terminator) is
 * derived here from the one real number that owns it, the mean sidereal day.
 */

const TWO_PI = Math.PI * 2;
const DEG = 180 / Math.PI;
const MS_PER_DAY = 86_400_000;
// Mean tropical year, for the low-precision solar declination below.
const DAYS_PER_YEAR = 365.2422;
const MU_EARTH_KM3_S2 = 398600.4418;

/**
 * Earth rotation angle in radians, in [0, 2π), at `simulationTimeS` seconds
 * since the epoch.
 *
 * One full 360° turn takes a mean sidereal day (86 164.0905 s), i.e. 15.041° of
 * rotation per hour of simulated time — the real spin relative to the inertial
 * frame. `simulationTimeS` is already warped by the clock, so the globe turns
 * faster at higher time-warps instead of running at a separate fixed speed.
 */
export function earthRotationAngleRad(simulationTimeS: number): number {
  const day = SCENE_CONFIG.units.secondsPerEarthSiderealDay;
  const turns = simulationTimeS / day;
  if (!Number.isFinite(turns)) return 0;
  // Take the fraction before scaling so a huge simulation time (1e6× warps)
  // does not lose precision to a giant angle.
  return ((turns % 1) + 1) % 1 * TWO_PI;
}

/** Geocentric latitude in degrees from an ECI position (km). */
export function eciLatitudeDeg(position: Vector3Km): number {
  const [x, y, z] = position;
  const r = Math.hypot(x, y, z);
  if (r === 0) return 0;
  return Math.asin(z / r) * DEG;
}

/**
 * Sub-satellite longitude in degrees, in (-180, 180].
 *
 * An ECI longitude is inertial; the geographic longitude is that angle minus the
 * angle Earth has turned through since the epoch. Without the subtraction a
 * satellite would appear to sit over the same ground point forever, which is
 * exactly the error that makes a ground track look static.
 */
export function eciLongitudeDeg(position: Vector3Km, simulationTimeS: number): number {
  const [x, y] = position;
  const inertialDeg = Math.atan2(y, x) * DEG;
  const spinDeg = earthRotationAngleRad(simulationTimeS) * DEG;
  return (((inertialDeg - spinDeg + 540) % 360) + 360) % 360 - 180;
}

/** Orbital period in seconds for a semi-major axis in km (two-body, mu Earth). */
export function orbitalPeriodS(semiMajorAxisKm: number): number {
  return TWO_PI * Math.sqrt(semiMajorAxisKm ** 3 / MU_EARTH_KM3_S2);
}

/**
 * Approximate solar declination in degrees for a simulated UTC instant.
 *
 * The obliquity of the ecliptic is 23.44° (WGS 84 / IAU 2006): the Sun's
 * declination swings between +23.44° at the June solstice and -23.44° at the
 * December one, and is ~0° at the equinoxes. In the ECI frame the pole is +Z by
 * definition, so the axial tilt shows up as this declination — it is what tilts
 * the day/night terminator across the globe.
 *
 * Low-precision almanac formula; good to about a degree, which is far finer
 * than the terminator is drawn.
 */
export function solarDeclinationDeg(epochUtc: string, simulationTimeS: number): number {
  const tilt = SCENE_CONFIG.earthRotation.axialTiltDeg;
  const epochMs = Date.parse(epochUtc);
  if (!Number.isFinite(epochMs) || !Number.isFinite(simulationTimeS)) return 0;
  const instant = epochMs + simulationTimeS * 1000;
  const date = new Date(instant);
  const time = date.getTime();
  if (!Number.isFinite(time)) return 0;
  const yearStart = Date.UTC(date.getUTCFullYear(), 0, 1);
  const dayOfYear = (time - yearStart) / MS_PER_DAY + 1;
  return -tilt * Math.cos((TWO_PI * (dayOfYear + 10)) / DAYS_PER_YEAR);
}
