import assert from "node:assert/strict";
import { test } from "node:test";
import type { SimulationConfig } from "../../contract";
import {
  definitionFields,
  getAtPath,
  issuesByPath,
  issuesForField,
  pathSegments,
  schemaDefault,
  updateAtPath,
  validateDraft,
  widgetKind,
} from "../schema";

const orbit = {
  semi_major_axis_km: 6928.137,
  eccentricity: 0.001,
  inclination_deg: 97.6,
  raan_deg: 0,
  argument_of_perigee_deg: 0,
  true_anomaly_deg: 0,
};

function config(): SimulationConfig {
  return {
    schema_version: "1.0.0",
    scenario_id: "editor-test",
    name: "Editor test",
    seed: 7,
    epoch_utc: "2026-10-12T00:00:00Z",
    time_scale: 300,
    satellites: [
      { id: "sat-alpha", name: "Alpha", orbit: { ...orbit } },
      { id: "sat-bravo", name: "Bravo", orbit: { ...orbit, true_anomaly_deg: 90 } },
    ],
  };
}

test("orbit fields come from the schema with units, steps and bounds", () => {
  const fields = definitionFields("OrbitElements", { pathPrefix: "satellites[0].orbit" });
  assert.equal(fields.length, 6);

  const semiMajor = fields.find((f) => f.key === "semi_major_axis_km")!;
  assert.equal(semiMajor.label, "Semi-major axis");
  assert.equal(semiMajor.unit, "km");
  assert.equal(semiMajor.step, 0.001);
  assert.equal(semiMajor.exclusiveMinimum, 6378.137);
  assert.equal(semiMajor.required, true);
  assert.equal(semiMajor.path, "satellites[0].orbit.semi_major_axis_km");
  assert.equal(semiMajor.widget, "number");

  const eccentricity = fields.find((f) => f.key === "eccentricity")!;
  assert.equal(eccentricity.exclusiveMaximum, 1);
  assert.equal(eccentricity.unit, undefined);
});

test("simulation fields carry metadata and read-only flags from the schema", () => {
  const fields = definitionFields("SimulationConfig");
  const byKey = new Map(fields.map((f) => [f.key, f]));

  assert.equal(byKey.get("time_scale")!.label, "Time scale");
  assert.equal(byKey.get("time_scale")!.unit, "×");
  assert.equal(byKey.get("time_scale")!.step, 1);
  assert.equal(byKey.get("time_scale")!.defaultValue, 1);
  assert.equal(byKey.get("time_scale")!.widget, "number");

  assert.equal(byKey.get("scenario_id")!.readOnly, true);
  assert.equal(byKey.get("scenario_id")!.widget, "readonly");
  assert.equal(byKey.get("schema_version")!.readOnly, true);
  assert.equal(byKey.get("epoch_utc")!.widget, "readonly");

  // Structured fields get an explicit unsupported kind rather than a text box.
  assert.equal(byKey.get("satellites")!.type, "unsupported");
  assert.equal(byKey.get("satellites")!.widget, "unsupported");
});

test("widget selection is keyed by schema kind, not parameter name", () => {
  const t = definitionFields("SimulationConfig").find((f) => f.key === "time_scale")!;
  const r = definitionFields("SimulationConfig").find((f) => f.key === "scenario_id")!;
  const u = definitionFields("SimulationConfig").find((f) => f.key === "satellites")!;
  assert.equal(widgetKind(t), "number");
  assert.equal(widgetKind(r), "readonly");
  assert.equal(widgetKind(u), "unsupported");
});

test("schema defaults are exposed for reset-to-default", () => {
  assert.equal(schemaDefault("SimulationConfig", "time_scale"), 1);
  assert.equal(schemaDefault("SimulationConfig", "scenario_id"), undefined);
});

test("draft updates are immutable and addressable by path", () => {
  const original = config();
  const updated = updateAtPath(original, "satellites[1].orbit.raan_deg", 120);
  assert.equal(original.satellites[1].orbit.raan_deg, 0);
  assert.equal(updated.satellites[1].orbit.raan_deg, 120);
  assert.equal(updated.satellites[0].orbit.raan_deg, 0);
  assert.equal(getAtPath(updated, "satellites[1].orbit.raan_deg"), 120);
  assert.deepEqual(pathSegments("satellites[1].orbit.raan_deg"), ["satellites", 1, "orbit", "raan_deg"]);
});

test("validation blocks out-of-range orbit values with field paths", () => {
  const bad = updateAtPath(config(), "satellites[0].orbit.eccentricity", 1.5);
  const issues = validateDraft(bad);
  assert.ok(issues.length > 0);
  const index = issuesByPath(issues);
  const messages = issuesForField(index, "satellites[0].orbit.eccentricity");
  assert.ok(messages.some((m) => m.includes("< 1")));

  assert.deepEqual(validateDraft(config()), []);
});

test("validation reports malformed values instead of silently accepting them", () => {
  const bad = updateAtPath(config(), "time_scale", 0);
  const index = issuesByPath(validateDraft(bad));
  assert.ok((index.get("time_scale") ?? []).some((m) => m.includes("> 0")));

  const badId = updateAtPath(config(), "satellites[0].id", "Not An Id");
  const idIssues = issuesByPath(validateDraft(badId));
  assert.ok((idIssues.get("satellites[0].id") ?? []).some((m) => m.includes("pattern")));
});
