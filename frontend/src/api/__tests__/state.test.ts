/**
 * Day 10: the state stream must never roll the UI backward.
 *
 * These tests exercise the pure guard and envelope parser used by App.tsx, with
 * snapshots shaped exactly like the core's `/api/state` payload.
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { ContractError, SCHEMA_VERSION } from "../../contract";
import { cursorOf, parseStateEnvelope, shouldAcceptState, type StateEnvelope } from "../state";

function snapshot(scenarioId: string, simulationTimeS: number) {
  return {
    schema_version: SCHEMA_VERSION,
    scenario_id: scenarioId,
    producer: { name: "constellab-core", version: "0.2.0" },
    clock: { epoch_utc: "2026-10-12T00:00:00Z", simulation_time_s: simulationTimeS, time_scale: 60, paused: false },
    satellites: [
      { id: "sat-alpha", position_eci_km: [6921.208863, 0, 0], velocity_eci_km_s: [0, -1.004180108, 7.525979851] },
    ],
  };
}

function envelope(revision: number, timeS: number, scenarioId = "visual-orbit-demo"): StateEnvelope {
  return parseStateEnvelope({
    request_id: `ui-${revision}`,
    revision,
    scenario_id: scenarioId,
    clock: snapshot(scenarioId, timeS).clock,
    snapshot: snapshot(scenarioId, timeS),
  });
}

test("the first state is always accepted", () => {
  assert.equal(shouldAcceptState(null, envelope(1, 0)), true);
});

test("a newer revision replaces the current state", () => {
  const first = envelope(4, 60);
  assert.equal(shouldAcceptState(cursorOf(first), envelope(5, 120)), true);
});

test("a late reply from an older revision is dropped", () => {
  const current = cursorOf(envelope(9, 540));
  assert.equal(shouldAcceptState(current, envelope(8, 480)), false);
});

test("an equal revision with an older clock is dropped", () => {
  const current = cursorOf(envelope(5, 300));
  assert.equal(shouldAcceptState(current, envelope(5, 299)), false);
});

test("a repeated revision is accepted so a paused tab keeps rendering", () => {
  const current = cursorOf(envelope(5, 300));
  assert.equal(shouldAcceptState(current, envelope(5, 300)), true);
});

test("a same-revision state from a different scenario is dropped", () => {
  const current = cursorOf(envelope(5, 300));
  assert.equal(shouldAcceptState(current, envelope(5, 0, "swarm-48")), false);
});

test("a scenario load is accepted because its revision moves forward", () => {
  const current = cursorOf(envelope(5, 300));
  // Restarting at t = 0 is newer state, not a rollback.
  assert.equal(shouldAcceptState(current, envelope(6, 0, "swarm-48")), true);
});

test("the envelope exposes exactly what the UI needs", () => {
  const state = envelope(3, 90);
  assert.equal(state.requestId, "ui-3");
  assert.equal(state.revision, 3);
  assert.equal(state.scenarioId, "visual-orbit-demo");
  assert.equal(state.snapshot.satellites[0].id, "sat-alpha");
  assert.equal(state.snapshot.clock.simulation_time_s, 90);
});

test("a malformed envelope is a contract violation, not a silent fallback", () => {
  const valid = {
    request_id: "ui-1", revision: 2, scenario_id: "visual-orbit-demo",
    snapshot: snapshot("visual-orbit-demo", 0),
  };
  for (const broken of [
    { ...valid, revision: 0 },
    { ...valid, revision: 2.5 },
    { ...valid, revision: "2" },
    { ...valid, request_id: "" },
    { ...valid, scenario_id: "" },
    { ...valid, snapshot: { ...valid.snapshot, schema_version: "9.0.0" } },
    { ...valid, scenario_id: "other-scenario" },
    null,
  ]) {
    assert.throws(() => parseStateEnvelope(broken), ContractError);
  }
});
