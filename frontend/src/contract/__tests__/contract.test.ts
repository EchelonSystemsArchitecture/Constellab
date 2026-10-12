/**
 * Contract tests: the TypeScript side must accept and reject exactly what the
 * Python core does, using the same fixtures. Run with `npm run test:contract`.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { test } from "node:test";

import {
  ContractError,
  SCHEMA_VERSION,
  SIMULATION_CONTRACT_SCHEMA,
  isCompatibleVersion,
  parseConfig,
  parseSnapshot,
} from "../index";

const ROOT = path.resolve(__dirname, "..", "..", "..", "..");
const DATA = path.join(ROOT, "core", "constellab_core", "data");
const FIXTURES = path.join(ROOT, "core", "tests", "fixtures");

const load = (file: string) => JSON.parse(readFileSync(file, "utf8"));
const issuePaths = (fn: () => unknown): Set<string> => {
  try {
    fn();
  } catch (err: unknown) {
    if (!(err instanceof ContractError)) throw new Error(`expected ContractError, got ${String(err)}`);
    return new Set(err.errors.map((e) => e.path));
  }
  throw new Error("expected a ContractError");
};

test("generated schema matches the Python source of truth", () => {
  const source = load(path.join(DATA, "simulation_contract.schema.json"));
  assert.deepEqual(SIMULATION_CONTRACT_SCHEMA, source);
  assert.equal(SCHEMA_VERSION, source["x-schema-version"]);
});

test("version compatibility rules", () => {
  const [major, minor] = SCHEMA_VERSION.split(".").map(Number);
  assert.ok(isCompatibleVersion(SCHEMA_VERSION));
  assert.ok(isCompatibleVersion(`${major}.${minor}.99`));
  assert.equal(isCompatibleVersion(`${major + 1}.0.0`), false);
  assert.equal(isCompatibleVersion(`${major}.${minor + 1}.0`), false);
  assert.equal(isCompatibleVersion("v1"), false);
  assert.equal(isCompatibleVersion(1), false);
});

test("built-in scenarios parse as configs and survive a JSON round-trip", () => {
  for (const file of ["scenario_empty.json", "scenario_four_satellites.json"]) {
    const raw = load(path.join(DATA, file));
    const config = parseConfig(raw);
    assert.deepEqual(parseConfig(JSON.parse(JSON.stringify(config))), config);
    const ids = config.satellites.map((s) => s.id);
    assert.equal(new Set(ids).size, ids.length, "ids must be unique");
  }
});

test("a snapshot built like the core's epoch snapshot parses", () => {
  const snapshot = parseSnapshot({
    schema_version: SCHEMA_VERSION,
    scenario_id: "visual-orbit-demo",
    producer: { name: "constellab-core", version: "0.2.0" },
    clock: { epoch_utc: "2026-10-12T00:00:00Z", simulation_time_s: 0, time_scale: 60, paused: true },
    satellites: [
      { id: "sat-alpha", position_eci_km: [6921.208863, 0, 0], velocity_eci_km_s: [0, -1.004180108, 7.525979851] },
    ],
  });
  assert.equal(snapshot.satellites[0].id, "sat-alpha");
  assert.equal(snapshot.satellites[0].position_eci_km.length, 3);
});

test("malformed configs fixture is rejected with the expected field paths", () => {
  for (const c of load(path.join(FIXTURES, "malformed_configs.json")).cases) {
    const paths = issuePaths(() => parseConfig(c.config));
    for (const expected of c.expect_paths) assert.ok(paths.has(expected), `${c.name}: expected ${expected} in ${[...paths]}`);
  }
});

test("malformed snapshots fixture is rejected with the expected field paths", () => {
  for (const c of load(path.join(FIXTURES, "malformed_snapshots.json")).cases) {
    const paths = issuePaths(() => parseSnapshot(c.snapshot));
    for (const expected of c.expect_paths) assert.ok(paths.has(expected), `${c.name}: expected ${expected} in ${[...paths]}`);
  }
});

test("all errors are reported at once", () => {
  const paths = issuePaths(() => parseConfig({ schema_version: SCHEMA_VERSION, scenario_id: "x", seed: -1, epoch_utc: "bad", satellites: [], extra: 1 }));
  assert.deepEqual([...paths].sort(), ["$.epoch_utc", "$.extra", "$.seed"]);
});
