import assert from "node:assert/strict";
import { test } from "node:test";
import type { SatelliteState, SimulationSnapshot } from "../../contract";
import { DEFAULT_DIAGNOSTIC_TOGGLES, diagnosticsModel, formatAge, snapshotAgeMs, stalenessTone, visibleLabelIds } from "../diagnostics";
import type { SatelliteProjection } from "../EarthScene";

function satellite(id: string, x = 6928.137): SatelliteState {
  return {
    id,
    position_eci_km: [x, 0, 0],
    velocity_eci_km_s: [0, 7.6, 0],
    orbit: {
      semi_major_axis_km: 6928.137,
      eccentricity: 0,
      inclination_deg: 53,
      raan_deg: 0,
      argument_of_perigee_deg: 0,
      true_anomaly_deg: 0,
    },
  };
}

const snapshot: SimulationSnapshot = {
  schema_version: "1.1.0",
  scenario_id: "visual-orbit-demo",
  producer: { name: "constellab-core", version: "0.3.0" },
  clock: { epoch_utc: "2026-10-12T00:00:00Z", simulation_time_s: 3600, time_scale: 300, paused: false },
  satellites: [satellite("sat-alpha"), satellite("sat-bravo", 7100)],
};

const ALL_ON = { ids: true, orbitPlane: true, simTime: true, selectedPosition: true, snapshotAge: true };

test("age is measured from the accepted snapshot and formatted without fake precision", () => {
  assert.equal(snapshotAgeMs(null, 1000), null);
  assert.equal(snapshotAgeMs(1000, 1420), 420);
  assert.equal(snapshotAgeMs(1200, 1000), 0, "clock skew never yields a negative age");
  assert.equal(formatAge(null), "UNAVAILABLE");
  assert.equal(formatAge(420), "420 ms");
  assert.equal(formatAge(3100), "3.1 s");
  assert.equal(formatAge(125_000), "2 m 05 s");
});

test("staleness thresholds come from renderer configuration", () => {
  assert.equal(stalenessTone(null), "muted");
  assert.equal(stalenessTone(120), "ok");
  assert.equal(stalenessTone(900), "warn");
  assert.equal(stalenessTone(5000), "bad");
});

test("every overlay toggle independently adds or removes its rows", () => {
  const base = diagnosticsModel({
    snapshot, toggles: { ...DEFAULT_DIAGNOSTIC_TOGGLES, simTime: false, selectedPosition: false, snapshotAge: false },
    receivedAtMs: 1000, nowMs: 1100, selectedId: "sat-alpha",
  });
  assert.deepEqual(base.rows, []);

  const simOnly = diagnosticsModel({
    snapshot, toggles: { ...ALL_ON, selectedPosition: false, snapshotAge: false, ids: false, orbitPlane: false },
    receivedAtMs: 1000, nowMs: 1100,
  });
  assert.deepEqual(simOnly.rows.map((row) => row.key), ["sim_utc", "sim_time"]);
  assert.equal(simOnly.rows[0].value, "2026-10-12T01:00:00Z");
  assert.match(simOnly.rows[1].value, /3600\.0 s/);
  assert.match(simOnly.rows[1].value, /×300/);

  const ageOnly = diagnosticsModel({
    snapshot, toggles: { ...ALL_ON, simTime: false, selectedPosition: false },
    receivedAtMs: 1000, nowMs: 4000, renderFps: 58.4,
  });
  assert.deepEqual(ageOnly.rows.map((row) => row.key), ["snapshot_age", "fleet", "render_fps"]);
  assert.equal(ageOnly.rows[0].value, "3.0 s");
  assert.equal(ageOnly.rows[0].tone, "bad");
  assert.equal(ageOnly.rows[1].value, "2 satellites");
  assert.equal(ageOnly.stale, true);
});

test("the selected position shows real ECI values, or UNAVAILABLE when nothing is selected", () => {
  const none = diagnosticsModel({
    snapshot, toggles: { ...ALL_ON, simTime: false, snapshotAge: false },
    receivedAtMs: 0, nowMs: 0, selectedId: null,
  });
  const byKey = Object.fromEntries(none.rows.map((row) => [row.key, row]));
  assert.equal(byKey.selection.value, "NONE");
  assert.equal(byKey.selection.available, false);
  assert.equal(byKey.selected_position.value, "UNAVAILABLE");
  assert.equal(byKey.selected_altitude.value, "UNAVAILABLE");

  const selected = diagnosticsModel({
    snapshot, toggles: { ...ALL_ON, simTime: false, snapshotAge: false },
    receivedAtMs: 0, nowMs: 0, selectedId: "sat-bravo",
  });
  const rows = Object.fromEntries(selected.rows.map((row) => [row.key, row]));
  assert.equal(rows.selection.value, "sat-bravo");
  assert.equal(rows.selected_position.value, "7100.0, 0.0, 0.0");
  assert.equal(rows.selected_altitude.value, "721.9 km");
});

test("a snapshot that is absent degrades to UNAVAILABLE instead of invented values", () => {
  const model = diagnosticsModel({ snapshot: null, toggles: ALL_ON, receivedAtMs: null, nowMs: 5, selectedId: "x" });
  for (const row of model.rows) {
    assert.equal(row.available, false, `${row.key} must be unavailable`);
    assert.equal(row.value, "UNAVAILABLE", `${row.key} must not fabricate a value`);
  }
  assert.equal(model.ageMs, null);
  assert.equal(model.stale, false);
});

function projection(id: string, isOccluded = false): SatelliteProjection {
  return {
    id, screenX: 0, screenY: 0, isOccluded,
    distanceKm: 6928, altitudeKm: 550, velocityKms: 7.6, colorHex: "#6f9b97", index: 0,
  };
}

test("id labels are bounded, skip occluded satellites and always keep the selection", () => {
  const four = [projection("a"), projection("b"), projection("c", true), projection("d")];
  assert.deepEqual(visibleLabelIds(four, { ...ALL_ON, ids: false }, "a"), []);
  assert.deepEqual(visibleLabelIds(four, ALL_ON, "a"), ["a", "b", "d"]);

  const fleet = Array.from({ length: 400 }, (_, i) => projection(`s${i}`));
  const labelled = visibleLabelIds(fleet, ALL_ON, "s399", 24);
  assert.equal(labelled.length, 24);
  assert.equal(labelled[0], "s399");
  assert.equal(new Set(labelled).size, labelled.length);
  assert.ok(labelled.some((id) => Number(id.slice(1)) > 300), "labels spread over the fleet");
});
