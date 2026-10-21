/**
 * Day 13: browser-independent end-to-end flow.
 *
 * A real core is started on an ephemeral port; every step goes through the same
 * client modules the app uses. WebGL rendering is out of scope for Node, so the
 * visual half is covered by the scene/fleet tests, the fleet benchmark and the
 * manual in-app check documented in the README.
 */
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import path from "node:path";
import { after, before, describe, test } from "node:test";
import { initialConnection, nextConnection, reconnectResetsCursor } from "../../api/connection";
import { cursorOf, parseStateEnvelope, shouldAcceptState, type StateEnvelope } from "../../api/state";
import type { SimulationClock } from "../../contract";
import { eciLatitudeDeg, eciLongitudeDeg } from "../../scene/earth";
import { resolveSelection, satelliteInspectorSections } from "../../scene/selection";
import { repoRoot, requestJson, runHeadless, sleep, startCore, type CoreHandle } from "../harness";

let core: CoreHandle;

const state = async (): Promise<StateEnvelope> => {
  const response = await requestJson(core.baseUrl, "GET", "/api/state");
  assert.equal(response.status, 200);
  return parseStateEnvelope(response.body);
};

const clock = async (): Promise<SimulationClock> => (await state()).snapshot.clock;

const postClock = async (action: string, body: object = {}) => {
  const response = await requestJson(core.baseUrl, "POST", `/api/clock/${action}`, body);
  assert.equal(response.status, 200, `${action} failed: ${JSON.stringify(response.body)}`);
  return response.body as SimulationClock;
};

before(async () => {
  core = await startCore("visual-orbit-demo");
});

after(async () => {
  await core?.stop();
});

describe("G0 vertical slice", () => {
  test("clean start serves a valid canonical state envelope with the configured fleet", async () => {
    const status = await requestJson<{ name: string; schema_version: string; status: string }>(
      core.baseUrl, "GET", "/api/status",
    );
    assert.equal(status.status, 200);
    assert.equal(status.body.name, "constellab-core");
    assert.equal(status.body.status, "ok");

    const response = await requestJson(core.baseUrl, "GET", "/api/state", undefined, { "X-Request-Id": "e2e-start-1" });
    assert.equal(response.status, 200);
    assert.equal(response.headers.get("x-request-id"), "e2e-start-1");
    assert.ok(Number.isFinite(Number(response.headers.get("x-revision"))));

    const envelope = parseStateEnvelope(response.body);
    const fixture = JSON.parse(readFileSync(
      path.join(repoRoot(), "core", "constellab_core", "data", "scenario_four_satellites.json"),
      "utf8",
    )) as { satellites: { id: string; orbit: { semi_major_axis_km: number } }[] };

    assert.equal(envelope.snapshot.scenario_id, "visual-orbit-demo");
    assert.deepEqual(
      envelope.snapshot.satellites.map((sat) => sat.id),
      fixture.satellites.map((sat) => sat.id),
      "ids come from config, never array position",
    );
    assert.equal(envelope.snapshot.clock.time_scale, 300);
    assert.equal(envelope.snapshot.clock.paused, false);
    for (const [index, sat] of envelope.snapshot.satellites.entries()) {
      const radius = Math.hypot(...sat.position_eci_km);
      const a = fixture.satellites[index].orbit.semi_major_axis_km;
      const e = sat.orbit?.eccentricity ?? 0;
      // The state must sit on its own element ellipse: perigee .. apogee.
      assert.ok(radius >= a * (1 - e) - 0.5, `${sat.id} inside perigee (${radius} km)`);
      assert.ok(radius <= a * (1 + e) + 0.5, `${sat.id} beyond apogee (${radius} km)`);
    }
  });

  test("simulated time advances at the clock's scale, and pause/step/reset are exact", async () => {
    await postClock("time_scale", { time_scale: 300 });
    const before = await clock();
    await sleep(500);
    const after = await clock();
    const elapsed = after.simulation_time_s - before.simulation_time_s;
    assert.ok(elapsed > 80 && elapsed < 260, `expected ~150 simulated seconds at ×300, got ${elapsed}`);

    // Pause freezes time; two polls are byte-identical on the clock.
    await postClock("pause");
    const pausedA = await clock();
    await sleep(250);
    const pausedB = await clock();
    assert.equal(pausedA.paused, true);
    assert.equal(pausedB.simulation_time_s, pausedA.simulation_time_s);

    // One step is exactly +1 s and never resumes the clock.
    const stepped = await postClock("step");
    assert.equal(stepped.simulation_time_s, pausedA.simulation_time_s + 1);
    assert.equal(stepped.paused, true);

    // Reset restores the scenario epoch exactly.
    const reset = await postClock("reset");
    assert.equal(reset.simulation_time_s, 0);
    assert.equal(reset.paused, true);
    assert.equal(reset.time_scale, 300);
    await postClock("resume");
    assert.equal((await clock()).paused, false);
  });

  test("time scale changes simulated time, not rendering math", async () => {
    await postClock("reset");
    await postClock("resume");
    await postClock("time_scale", { time_scale: 1 });
    // The core eases the advance rate into a new scale (Day 6 smoothing), so let
    // it settle before measuring the steady-state rate.
    await sleep(2500);
    const slowStart = await clock();
    await sleep(800);
    const slowEnd = await clock();

    const reply = await postClock("time_scale", { time_scale: 1000 });
    assert.equal(reply.time_scale, 1000, "the requested scale is reported immediately");
    await sleep(2500);
    const fastStart = await clock();
    await sleep(800);
    const fastEnd = await clock();

    const slow = slowEnd.simulation_time_s - slowStart.simulation_time_s;
    const fast = fastEnd.simulation_time_s - fastStart.simulation_time_s;
    assert.ok(slow > 0.1 && slow < 3, `slow rate should track wall time, got ${slow}`);
    assert.ok(fast > slow * 50, `×1000 (${fast}) must clearly outrun ×1 (${slow})`);
    await postClock("time_scale", { time_scale: 300 });
    await postClock("reset");
  });

  test("a scenario reload replaces the fleet, keeps ids stable and yields usable inspector data", async () => {
    const load = await requestJson<{ scenario: { satellites: unknown[] } }>(
      core.baseUrl, "POST", "/api/scenario", { key: "swarm-1000" },
    );
    assert.equal(load.status, 200);
    assert.equal(load.body.scenario.satellites.length, 1000);

    const envelope = await state();
    assert.equal(envelope.snapshot.satellites.length, 1000);
    assert.equal(new Set(envelope.snapshot.satellites.map((sat) => sat.id)).size, 1000);

    // Selection by id works at fleet scale and never mutates state.
    const selected = resolveSelection("wl-0500", envelope.snapshot.satellites);
    assert.equal(selected.kind, "selected");
    assert.ok(selected.kind === "selected");
    const sections = satelliteInspectorSections(selected.satellite, envelope.snapshot.clock, envelope.snapshot);
    assert.ok(sections.length > 0);
    const altitude = sections.flatMap((section) => section.rows).find((row) => row.key === "altitude");
    assert.equal(altitude?.available, true);
    assert.match(altitude?.value ?? "", /^\d/);

    // Ground-track coordinates are real geographic values for a 53° shell.
    const latitude = eciLatitudeDeg(selected.satellite.position_eci_km);
    const longitude = eciLongitudeDeg(selected.satellite.position_eci_km, envelope.snapshot.clock.simulation_time_s);
    assert.ok(Math.abs(latitude) <= 53.01, `latitude ${latitude} outside the 53° inclination`);
    assert.ok(longitude >= -180 && longitude < 180);

    // Selection did not move time forward or change the fleet.
    const again = await state();
    assert.equal(again.snapshot.satellites.length, 1000);

    const back = await requestJson(core.baseUrl, "POST", "/api/scenario", { key: "visual-orbit-demo" });
    assert.equal(back.status, 200);
    assert.equal((await state()).snapshot.satellites.length, 4);
  });

  test("an invalid config is rejected with field paths and leaves the run untouched", async () => {
    const fixture = JSON.parse(readFileSync(
      path.join(repoRoot(), "core", "constellab_core", "data", "scenario_four_satellites.json"),
      "utf8",
    )) as Record<string, unknown> & { satellites: { orbit: Record<string, number> }[] };
    const before = await state();

    const badOrbit = structuredClone(fixture);
    badOrbit.satellites[0].orbit.eccentricity = 1.5;
    const rejected = await requestJson<{ error: string; errors: { path: string; message: string }[] }>(
      core.baseUrl, "POST", "/api/scenario", { config: badOrbit },
    );
    assert.equal(rejected.status, 422);
    assert.equal(rejected.body.error, "invalid_config");
    assert.ok(
      rejected.body.errors.some((error) => error.path.includes("eccentricity")),
      `expected an eccentricity field path, got ${JSON.stringify(rejected.body.errors)}`,
    );

    const unknownField = structuredClone(fixture) as Record<string, unknown>;
    unknownField.evil = "rm -rf /";
    const unknown = await requestJson<{ errors: { path: string }[] }>(
      core.baseUrl, "POST", "/api/scenario", { config: unknownField },
    );
    assert.equal(unknown.status, 422);
    assert.ok(unknown.body.errors.some((error) => error.path.includes("evil")));

    const after = await state();
    assert.equal(after.snapshot.scenario_id, before.snapshot.scenario_id);
    assert.equal(after.snapshot.satellites.length, before.snapshot.satellites.length);
  });

  test("a restarted core is accepted once the client forgets its old revision epoch", async () => {
    const first = await state();
    const restarted = await startCore("visual-orbit-demo");
    try {
      const freshResponse = await requestJson(restarted.baseUrl, "GET", "/api/state");
      const fresh = parseStateEnvelope(freshResponse.body);
      // A fresh process starts its revision counter again; the old cursor would
      // drop every reply as stale without the reconnect rule.
      assert.equal(shouldAcceptState(cursorOf(first), fresh), false);
      let connection = nextConnection(initialConnection(), { type: "ok", atMs: 0 });
      const down = nextConnection(connection, { type: "failure", atMs: 100, message: "core restarted" });
      connection = nextConnection(down, { type: "ok", atMs: 200 });
      assert.equal(reconnectResetsCursor(down, connection), true);
      assert.equal(shouldAcceptState(null, fresh), true);
    } finally {
      await restarted.stop();
    }
  });

  test("headless runs are byte-for-byte reproducible", async () => {
    const first = runHeadless("visual-orbit-demo", 60, 10);
    const second = runHeadless("visual-orbit-demo", 60, 10);
    const hash = (text: string) => createHash("sha256").update(text).digest("hex");
    assert.equal(first.length > 0, true);
    assert.equal(hash(first), hash(second), "same config/time/seed must produce the same trace");
    assert.equal(first.split("\n").filter(Boolean).length, 7);
  });
});
