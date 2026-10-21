import assert from "node:assert/strict";
import { test } from "node:test";
import { Matrix4, Scene, Vector3 } from "three";
import type { OrbitElements, SimulationSnapshot } from "../../contract";
import { SCENE_CONFIG } from "../config";
import { FleetRenderer, orbitSignature, pathSegmentsFor, selectPathKeys } from "../fleet";
import { eciToScene } from "../orbit";

function walkerOrbit(plane: number, slot: number, planes: number, count: number): OrbitElements {
  return {
    semi_major_axis_km: 6928.137,
    eccentricity: 0,
    inclination_deg: 53,
    raan_deg: (plane * 360) / planes,
    argument_of_perigee_deg: 0,
    true_anomaly_deg: (slot * 360) / (count / planes) + (plane * 360) / count,
  };
}

/** Snapshot with circular positions at `timeS`, no propagation model needed. */
function walkerSnapshot(count: number, planes: number, timeS = 0): SimulationSnapshot {
  const satellites = Array.from({ length: count }, (_, index) => {
    const orbit = walkerOrbit(index % planes, Math.floor(index / planes), planes, count);
    const angle = (orbit.true_anomaly_deg * Math.PI) / 180 + (timeS / 5700) * Math.PI * 2;
    const radius = orbit.semi_major_axis_km;
    return {
      id: `wl-${String(index).padStart(4, "0")}`,
      position_eci_km: [radius * Math.cos(angle), radius * Math.sin(angle), 0] as [number, number, number],
      velocity_eci_km_s: [0, 7.6, 0] as [number, number, number],
      orbit,
    };
  });
  return {
    schema_version: "1.1.0",
    scenario_id: `walker-${count}`,
    producer: { name: "test", version: "1" },
    clock: { epoch_utc: "2026-10-12T00:00:00Z", simulation_time_s: timeS, time_scale: 60, paused: false },
    satellites,
  };
}

test("path tessellation is tiered by fleet size and never grows with the fleet", () => {
  assert.equal(pathSegmentsFor(4), 180);
  assert.equal(pathSegmentsFor(48), 120);
  assert.equal(pathSegmentsFor(100), 72);
  assert.equal(pathSegmentsFor(500), 48);
  assert.equal(pathSegmentsFor(1000), 48);
  assert.equal(pathSegmentsFor(5000), 48);
  for (const count of [4, 48, 100, 500, 1000]) {
    assert.ok(pathSegmentsFor(count) <= 180);
  }
});

test("orbit signature identifies a conic, not a satellite position", () => {
  const base = walkerOrbit(0, 0, 10, 100);
  assert.equal(
    orbitSignature(base),
    orbitSignature({ ...base, true_anomaly_deg: 180 }),
    "same conic with a different anomaly is the same drawn path",
  );
  assert.notEqual(orbitSignature(base), orbitSignature({ ...base, raan_deg: 36 }));
  assert.notEqual(orbitSignature(base), orbitSignature({ ...base, semi_major_axis_km: 6978 }));
});

test("path budget spreads the retained planes and always keeps the pinned one", () => {
  const keys = Array.from({ length: 100 }, (_, i) => `key-${i}`);
  const chosen = selectPathKeys(keys, 10);
  assert.equal(chosen.length, 10);
  assert.equal(new Set(chosen).size, 10);
  assert.ok(chosen.includes("key-90"), "the last planes must be represented, not only the first ten");
  const pinned = selectPathKeys(keys, 10, "key-97");
  assert.ok(pinned.includes("key-97"));
  assert.equal(pinned.length, 10);
  assert.deepEqual(selectPathKeys(keys, 1000), keys);
  assert.deepEqual(selectPathKeys(keys, 0), []);
});

test("1,000 satellites cost one instanced marker mesh and one path per plane", () => {
  const scene = new Scene();
  const fleet = new FleetRenderer(scene);
  fleet.setSnapshot(walkerSnapshot(1000, 25));
  const stats = fleet.stats();
  assert.equal(stats.satellites, 1000);
  assert.equal(stats.markerInstances, 1000);
  assert.equal(stats.uniqueOrbits, 25);
  assert.equal(stats.orbitPaths, 25);
  assert.equal(stats.markerDetail, "low");
  assert.equal(stats.pathSegments, 48);
  // 25 path lines + 1 marker mesh + 1 selection reticle. No per-satellite object.
  assert.equal(fleet.children(), 27);
  assert.equal(fleet.instanceIndex("wl-0000"), 0);
  assert.equal(fleet.instanceIndex("wl-0999"), 999);
  fleet.dispose();
  assert.equal(scene.children.length, 0);
});

test("instance slots are stable across updates and removals", () => {
  const scene = new Scene();
  const fleet = new FleetRenderer(scene);
  const first = walkerSnapshot(12, 3);
  fleet.setSnapshot(first);
  const slots = new Map(first.satellites.map((sat) => [sat.id, fleet.instanceIndex(sat.id)]));

  // Advance time: same ids, same slots, new positions.
  const later = walkerSnapshot(12, 3, 120);
  fleet.setSnapshot(later);
  for (const [id, slot] of slots) assert.equal(fleet.instanceIndex(id), slot);

  // Remove one satellite: every survivor keeps its slot.
  const trimmed = { ...later, satellites: later.satellites.filter((sat) => sat.id !== "wl-0003") };
  fleet.setSnapshot(trimmed);
  assert.equal(fleet.instanceIndex("wl-0003"), null);
  for (const [id, slot] of slots) {
    if (id === "wl-0003") continue;
    assert.equal(fleet.instanceIndex(id), slot);
  }
  fleet.dispose();
});

test("marker instances follow the snapshot and the selected one is enlarged", () => {
  const scene = new Scene();
  const fleet = new FleetRenderer(scene);
  const snapshot = walkerSnapshot(6, 2);
  fleet.setSnapshot(snapshot);

  const position = fleet.positionOf("wl-0002");
  assert.ok(position);
  const expected = eciToScene(snapshot.satellites[2].position_eci_km);
  assert.ok(position.distanceTo(expected) < 1e-9);

  const scaleOf = (id: string) => {
    const matrix = fleet.instanceMatrix(id);
    assert.ok(matrix);
    return new Vector3().setFromMatrixScale(matrix).x;
  };
  assert.ok(Math.abs(scaleOf("wl-0002") - 1) < 1e-9);
  fleet.setSelection("wl-0002");
  // Instance matrices are Float32 in the GPU buffer.
  assert.ok(Math.abs(scaleOf("wl-0002") - SCENE_CONFIG.fleet.selectionScale) < 1e-5);
  assert.ok(Math.abs(scaleOf("wl-0003") - 1) < 1e-5);

  // The selected orbit plane layer is created for the selection and moves with it.
  fleet.setSelection("wl-0004");
  assert.equal(fleet.children(), 5, "4 unique paths + markers + selection + one plane layer");
  fleet.dispose();
});

test("repeated snapshots and scenario switches do not grow scene objects", () => {
  const scene = new Scene();
  const fleet = new FleetRenderer(scene);
  fleet.setSnapshot(walkerSnapshot(1000, 25));
  const steady = fleet.children();
  for (let i = 0; i < 40; i++) fleet.setSnapshot(walkerSnapshot(1000, 25, i * 10));
  assert.equal(fleet.children(), steady);
  assert.equal(fleet.stats().orbitPaths, 25);

  // A scenario switch reuses the marker mesh and replaces the paths, not adds.
  for (let i = 0; i < 10; i++) {
    fleet.setSnapshot(walkerSnapshot(4, 2));
    fleet.setSnapshot(walkerSnapshot(1000, 25));
  }
  assert.equal(fleet.children(), steady);
  assert.equal(fleet.stats().satellites, 1000);
  assert.equal(fleet.stats().orbitPaths, 25);

  // Empty snapshot keeps the allocated instances but draws no paths and no markers.
  fleet.setSnapshot(walkerSnapshot(4, 2));
  fleet.setSnapshot(null);
  assert.equal(fleet.stats().satellites, 0);
  assert.equal(fleet.stats().orbitPaths, 0);
  assert.deepEqual(fleet.ids(), []);
  fleet.dispose();
});

test("selection matrix write does not mutate a rendered satellite's slot", () => {
  const scene = new Scene();
  const fleet = new FleetRenderer(scene);
  fleet.setSnapshot(walkerSnapshot(20, 4));
  const slot = fleet.instanceIndex("wl-0011");
  fleet.setSelection("wl-0011");
  assert.equal(fleet.instanceIndex("wl-0011"), slot);
  const matrix = fleet.instanceMatrix("wl-0011") as Matrix4;
  const position = new Vector3().setFromMatrixPosition(matrix);
  assert.ok(position.length() > 0);
  fleet.dispose();
});
