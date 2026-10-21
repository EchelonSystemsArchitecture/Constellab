import assert from "node:assert/strict";
import { test } from "node:test";
import { SCENE_CONFIG } from "../config";
import {
  earthRotationAngleRad,
  eciLatitudeDeg,
  eciLongitudeDeg,
  orbitalPeriodS,
  solarDeclinationDeg,
} from "../earth";

const DAY = SCENE_CONFIG.units.secondsPerEarthSiderealDay;
const TWO_PI = Math.PI * 2;
const DEG = 180 / Math.PI;

test("Earth turns once per mean sidereal day, i.e. 15.041° per hour", () => {
  // One hour of real-world rotation is 360/23.93447 h = 15.0411°.
  assert.ok(Math.abs(earthRotationAngleRad(3600) * DEG - 15.0411) < 1e-3);
  assert.ok(Math.abs(earthRotationAngleRad(DAY / 2) - Math.PI) < 1e-12);
  assert.ok(Math.abs(earthRotationAngleRad(DAY) - 0) < 1e-12);
  // The angle is always in [0, 2π), even after many turns (1e6× warps).
  for (const t of [0, 1, 3600, DAY * 7.5, 3.6e9]) {
    const angle = earthRotationAngleRad(t);
    assert.ok(angle >= 0 && angle < TWO_PI, `angle ${angle} out of range at t=${t}`);
  }
  assert.ok(Math.abs(earthRotationAngleRad(DAY * 3 + 3600) * DEG - 15.0411) < 1e-3);
});

test("a 36 000× warp sweeps the globe 150° per real second", () => {
  // 36 000 simulated seconds per real second = 10 simulated hours.
  const perRealSecond = earthRotationAngleRad(0 + 36_000 * 1) * DEG;
  assert.ok(Math.abs(perRealSecond - 150.411) < 1e-2, `got ${perRealSecond}`);
});

test("sub-satellite longitude is the inertial angle minus the planet's spin", () => {
  const position: [number, number, number] = [7000, 0, 0];
  assert.equal(eciLongitudeDeg(position, 0), 0);
  assert.ok(Math.abs(eciLongitudeDeg(position, DAY / 4) - -90) < 1e-9);
  assert.ok(Math.abs(eciLongitudeDeg(position, DAY / 2) - -180) < 1e-9);
  // Longitudes stay wrapped to (-180, 180].
  for (const t of [0, DAY / 3, DAY * 2.3, 12_345.6]) {
    const lon = eciLongitudeDeg([1234, -5678, 4321], t);
    assert.ok(lon > -180 && lon <= 180, `longitude ${lon} out of range at t=${t}`);
  }
});

test("latitude comes from the ECI z component and ignores the spin", () => {
  assert.ok(Math.abs(eciLatitudeDeg([0, 0, 7000]) - 90) < 1e-12);
  assert.ok(Math.abs(eciLatitudeDeg([7000, 0, 0])) < 1e-12);
  assert.equal(eciLatitudeDeg([0, 0, 0]), 0);
});

test("orbital period matches the two-body value for a 550 km orbit", () => {
  // a = 6928.137 km -> ~5 740 s (95.7 min).
  const period = orbitalPeriodS(6928.137);
  assert.ok(period > 5600 && period < 5850, `period ${period}`);
});

test("solar declination follows the 23.44° obliquity through the seasons", () => {
  const tilt = SCENE_CONFIG.earthRotation.axialTiltDeg;
  assert.equal(tilt, 23.44);
  const june = solarDeclinationDeg("2026-06-21T12:00:00Z", 0);
  const december = solarDeclinationDeg("2026-12-21T12:00:00Z", 0);
  const march = solarDeclinationDeg("2026-03-20T12:00:00Z", 0);
  assert.ok(Math.abs(june - tilt) < 0.3, `June solstice ${june}`);
  assert.ok(Math.abs(december + tilt) < 0.3, `December solstice ${december}`);
  assert.ok(Math.abs(march) < 1.5, `March equinox ${march}`);
  // The declination advances with simulated time: half a year flips the sign.
  const halfYearS = 182.6 * 86_400;
  assert.ok(solarDeclinationDeg("2026-06-21T12:00:00Z", halfYearS) < 0);
});

test("solar declination degrades safely on an unusable epoch", () => {
  assert.equal(solarDeclinationDeg("not-a-date", 0), 0);
  assert.equal(solarDeclinationDeg("2026-06-21T12:00:00Z", Number.NaN), 0);
});
