import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { test } from "node:test";
import { PerspectiveCamera, Vector3 } from "three";
import type { SatelliteState, SimulationSnapshot } from "../../contract";
import { parseSnapshot } from "../../contract";
import type { SatelliteProjection } from "../EarthScene";
import {
  EARTH_RADIUS_KM,
  focusCamera,
  pickSatellite,
  resolveSelection,
  satelliteInspectorSections,
  simulationUtc,
} from "../selection";

const ROOT = path.resolve(__dirname, "..", "..", "..", "..");

function snapshotAt(timeS: number): SimulationSnapshot {
  const raw = JSON.parse(
    readFileSync(path.join(ROOT, "core", "constellab_core", "data", "scenario_four_satellites.json"), "utf8"),
  ) as { satellites: { id: string }[] };
  const satellites: SatelliteState[] = raw.satellites.map((sat, i) => ({
    id: sat.id,
    position_eci_km: [7000 + i * 10, 1200, -300],
    velocity_eci_km_s: [-1, 7.3, 0.2],
  }));
  return parseSnapshot({
    schema_version: "1.0.0",
    scenario_id: "visual-orbit-demo",
    producer: { name: "constellab-core", version: "0.3.0" },
    clock: { epoch_utc: "2026-10-12T00:00:00Z", simulation_time_s: timeS, time_scale: 300, paused: false },
    satellites,
  });
}

function projection(id: string, screenX: number, screenY: number, isOccluded = false): SatelliteProjection {
  return {
    id, screenX, screenY, isOccluded,
    distanceKm: 7000, altitudeKm: 622, velocityKms: 7.5, colorHex: "#6F9B97", index: 0,
  };
}

test("selection resolves to the current snapshot and refuses stale ids", () => {
  const snapshot = snapshotAt(10);
  const first = snapshot.satellites[0];
  const selected = resolveSelection(first.id, snapshot.satellites);
  assert.equal(selected.kind, "selected");
  assert.equal(selected.kind === "selected" ? selected.satellite.id : null, first.id);

  assert.deepEqual(resolveSelection(null, snapshot.satellites), { kind: "none" });
  assert.deepEqual(resolveSelection("sat-gone", snapshot.satellites), { kind: "missing", id: "sat-gone" });
});

test("inspector renders every snapshot field and never leaks the previous satellite", () => {
  const snapshot = snapshotAt(10);
  const [alpha, bravo] = snapshot.satellites;

  const alphaRows = satelliteInspectorSections(alpha, snapshot.clock, snapshot).flatMap((s) => s.rows);
  const bravoRows = satelliteInspectorSections(bravo, snapshot.clock, snapshot).flatMap((s) => s.rows);

  const idOf = (rows: typeof alphaRows) => rows.find((r) => r.key === "id")?.value;
  assert.equal(idOf(alphaRows), alpha.id);
  assert.equal(idOf(bravoRows), bravo.id);

  // Switching selection replaces the whole value set: no alpha values remain.
  assert.ok(!bravoRows.some((r) => r.key === "position_x" && r.value === alphaRows.find((x) => x.key === "position_x")!.value));

  addOrbit(alpha);
  const withOrbit = satelliteInspectorSections(alpha, snapshot.clock, snapshot).flatMap((s) => s.rows);
  const eccentricity = withOrbit.find((r) => r.key === "eccentricity")!;
  assert.equal(eccentricity.available, true);
  assert.equal(eccentricity.value, "0.00100");
});

function addOrbit(satellite: SatelliteState) {
  // The orbit is optional in the contract; build a typed instance for the check above.
  (satellite as SatelliteState).orbit = {
    semi_major_axis_km: 6928.137,
    eccentricity: 0.001,
    inclination_deg: 97.6,
    raan_deg: 0,
    argument_of_perigee_deg: 0,
    true_anomaly_deg: 0,
  };
}

test("missing orbit elements show UNAVAILABLE, not zero", () => {
  const snapshot = snapshotAt(0);
  const satellite = { ...snapshot.satellites[2], orbit: undefined };
  const rows = satelliteInspectorSections(satellite, snapshot.clock, snapshot).flatMap((s) => s.rows);
  for (const key of ["semi_major_axis_km", "eccentricity", "inclination_deg", "raan_deg", "argument_of_perigee_deg", "true_anomaly_deg"]) {
    const row = rows.find((r) => r.key === key)!;
    assert.equal(row.available, false, key);
    assert.equal(row.value, "UNAVAILABLE", key);
  }
});

test("inspector derives radius, altitude and sim UTC from the snapshot clock", () => {
  const snapshot = snapshotAt(3600);
  const satellite = snapshot.satellites[0];
  const rows = satelliteInspectorSections(satellite, snapshot.clock, snapshot).flatMap((s) => s.rows);

  const radius = Math.hypot(...satellite.position_eci_km);
  assert.equal(rows.find((r) => r.key === "radius")!.value, radius.toFixed(3));
  assert.equal(rows.find((r) => r.key === "altitude")!.value, (radius - EARTH_RADIUS_KM).toFixed(1));
  assert.equal(rows.find((r) => r.key === "sim_utc")!.value, "2026-10-12T01:00:00Z");
  assert.equal(rows.find((r) => r.key === "simulation_time_s")!.value, "3600.0");
});

test("simulationUtc reports UNAVAILABLE for an unusable clock", () => {
  assert.equal(simulationUtc(null), "UNAVAILABLE");
  assert.equal(simulationUtc({ epoch_utc: "not-a-date", simulation_time_s: 0, time_scale: 1, paused: true }), "UNAVAILABLE");
});

test("picking returns the nearest visible marker and ignores occluded ones", () => {
  const projections = [projection("a", 100, 100), projection("b", 112, 108), projection("hidden", 100, 100, true)];
  assert.equal(pickSatellite(projections, 104, 103, 18), "a");
  assert.equal(pickSatellite(projections, 200, 200, 18), null);
  // An occluded marker at the click point is never picked, even if it is closest.
  assert.equal(pickSatellite([projection("hidden", 50, 50, true)], 50, 50, 18), null);
});

test("focus keeps direction and clamps distance to the configured bounds", () => {
  const camera = new PerspectiveCamera(45, 1, 0.01, 100);
  const controls = { target: new Vector3(0, 0, 0) };
  camera.position.set(3, 1.8, 3);
  camera.lookAt(0, 0, 0);
  const direction = camera.position.clone().normalize();

  const target = new Vector3(0.4, -0.2, 0.6);
  const distance = focusCamera(camera, controls, target, 2.5);
  assert.equal(distance, 2.5);
  assert.ok(controls.target.distanceTo(target) < 1e-12);
  assert.ok(Math.abs(camera.position.distanceTo(target) - 2.5) < 1e-9);
  assert.ok(camera.position.clone().sub(target).normalize().distanceTo(direction) < 1e-9);

  // Extreme requests clamp instead of leaving the camera outside its orbit shell.
  assert.ok(focusCamera(camera, controls, target, 1e6) <= 12);
  assert.ok(focusCamera(camera, controls, target, 1e-6) >= 1.35);
});

test("selection and camera focus never mutate simulation state", () => {
  const snapshot = snapshotAt(1234.5);
  const before = JSON.stringify(snapshot);

  const selected = resolveSelection(snapshot.satellites[1].id, snapshot.satellites);
  if (selected.kind === "selected") {
    satelliteInspectorSections(selected.satellite, snapshot.clock, snapshot);
    simulationUtc(snapshot.clock);
  }
  const camera = new PerspectiveCamera(45, 1, 0.01, 100);
  camera.position.set(3, 1.8, 3);
  focusCamera(camera, { target: new Vector3() }, new Vector3(0.2, 0.3, 0.5), 3);

  assert.equal(JSON.stringify(snapshot), before);
  assert.equal(snapshot.clock.simulation_time_s, 1234.5);
});
