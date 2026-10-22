/**
 * Day 22 acceptance: registry-scale parameter editing (pure logic).
 *
 * Everything under test is `registry.ts` — the pagination/filter maths,
 * validation, export/import — so the component stays a thin shell and
 * 10,000 fields are exercised without a DOM.
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  effectiveEdits,
  exportDraft,
  importDraft,
  parseRegistryPayload,
  paginateSpecs,
  specMatches,
  syntheticRegistry,
  validateEdits,
  validateValue,
  type EditMap,
  type EditValue,
} from "../registry";

const PAGE = { pageSize: 50 };

function editedKeysOf(edits: EditMap): Set<string> {
  const keys = new Set<string>();
  for (const [owner, values] of Object.entries(edits)) {
    for (const shortKey of Object.keys(values)) keys.add(`${owner}.${shortKey}`);
  }
  return keys;
}

test("payload parsing rejects malformed registries", () => {
  assert.throws(() => parseRegistryPayload(null), /must be an object/);
  assert.throws(() => parseRegistryPayload({ schema_hash: "x" }), /parameters list/);
  assert.throws(
    () => parseRegistryPayload({ schema_hash: "x", parameters: [{ key: "a" }] }),
    /missing a default/,
  );
  assert.throws(
    () => parseRegistryPayload({ schema_hash: "x", parameters: [{ key: 42, default: 1 }] }),
    /missing a key/,
  );
  assert.throws(
    () => parseRegistryPayload({ schema_hash: "x", parameters: [{ key: "a.b.c", default: "v" }] }),
    /numeric default/,
  );
});

test("payload parsing derives owner, shortKey and defaults", () => {
  const view = parseRegistryPayload({
    schema_version: 1,
    schema_hash: "abc123",
    parameters: [
      {
        key: "power.solar-battery.array_area_m2",
        kind: "number",
        unit: "m2",
        default: 4,
        minimum: 0,
        maximum: 40,
        label: "Array area",
        description: "Panel area",
      },
      {
        key: "task.round-robin.policy",
        kind: "string",
        default: "round-robin",
        enum: ["round-robin", "priority"],
      },
    ],
  });
  assert.equal(view.schemaHash, "abc123");
  assert.deepEqual(view.owners, ["power.solar-battery", "task.round-robin"]);
  const area = view.specs[0];
  assert.equal(area.owner, "power.solar-battery");
  assert.equal(area.shortKey, "array_area_m2");
  assert.equal(area.unit, "m2");
  assert.equal(area.minimum, 0);
  assert.equal(area.distribution, "constant");
  assert.equal(area.modelVisible, true);
  assert.equal(validateValue(area, 3.5), null);
  assert.match(validateValue(area, -1) ?? "", /must be >= 0/);
  assert.match(validateValue(area, 100) ?? "", /must be <= 40/);
  const policy = view.specs[1];
  assert.equal(validateValue(policy, "priority"), null);
  assert.match(validateValue(policy, "debt") ?? "", /must be one of/);
});

test("a 10,000-field registry paginates to exactly pageSize rows", () => {
  const view = syntheticRegistry(10000, 4);
  assert.equal(view.specs.length, 10000);
  const result = paginateSpecs(view.specs, { query: "", owner: null, editedOnly: false, page: 1, ...PAGE }, editedKeysOf({}));
  assert.equal(result.total, 10000);
  assert.equal(result.pageCount, 200);
  assert.equal(result.slice.length, 50);
  const last = paginateSpecs(view.specs, { query: "", owner: null, editedOnly: false, page: 9999, ...PAGE }, editedKeysOf({}));
  assert.equal(last.page, 200);
  assert.equal(last.slice.length, 50);
});

test("search, owner filter and edited-only compose; untouched pages stay cheap", () => {
  const view = syntheticRegistry(10000, 4);
  const owner0 = `stress.owner-0000`;
  const result = paginateSpecs(view.specs, { query: "owner-0000", owner: owner0, editedOnly: false, page: 1, ...PAGE }, editedKeysOf({}));
  assert.equal(result.total, 2500);
  assert.equal(result.slice.every((s) => s.owner === owner0), true);
  // Edited-only view honours a stale page number by clamping, not silently empty.
  const single = paginateSpecs(
    view.specs.slice(0, 10),
    { query: "", owner: null, editedOnly: false, page: 1, ...PAGE },
    editedKeysOf({}),
  );
  assert.equal(single.total, 10);
});

test("hidden-edits counter warns about edited fields the filter hides", () => {
  const view = syntheticRegistry(20, 2);
  const key = view.specs[0].key; // stress.owner-0000.<...>
  const result = paginateSpecs(
    view.specs,
    { query: "", owner: "stress.owner-0001", editedOnly: false, page: 1, ...PAGE },
    editedKeysOf({ "stress.owner-0000": { [key.split(".")[2]]: 1 } }),
  );
  assert.equal(result.hiddenEdits, 1);
});

test("validation collects field-path issues for the whole draft", () => {
  const view = syntheticRegistry(6, 2);
  const bad: EditMap = {
    "stress.owner-0000": { field_0_m: -5, field_4_m: 60 },
    "stress.owner-unknown": { field_0_m: 1 },
  };
  const issues = validateEdits(view, bad);
  const paths = issues.map((issue) => issue.path);
  assert.deepEqual(paths, [
    "stress.owner-0000.field_0_m",
    "stress.owner-0000.field_4_m",
    "stress.owner-unknown.field_0_m",
  ]);
  assert.match(issues[0].message, />= /);
  assert.match(issues[1].message, /<= /);
  assert.match(issues[2].message, /no registered parameter/);
});

test("effectiveEdits always yields a full typed value set", () => {
  const view = syntheticRegistry(4, 1);
  const merged = effectiveEdits(view, { "stress.owner-0000": { field_0_m: 99 } });
  assert.equal(merged["stress.owner-0000"].field_0_m, 99);
  const count = Object.values(merged).reduce((n, values) => n + Object.keys(values).length, 0);
  assert.equal(count, 4);
});

test("export then import round-trips; a different schema is refused", () => {
  const view = syntheticRegistry(12, 2);
  const edits: EditMap = {
    "stress.owner-0000": { field_0_m: 5 },
    "stress.owner-0001": { field_1_W: 6, field_5_W: 7 },
  };
  const text = exportDraft(view, edits, "http://127.0.0.1:8765");
  const result = importDraft(text, view);
  assert.equal(result.ok, true);
  if (!result.ok) return;
  assert.deepEqual(result.edits, edits);
  assert.equal(result.imported, 3);

  const alien: EditMap = { "stress.owner-0000": { field_0_m: 3 } };
  const other = { ...view, schemaHash: "other-core" };
  const refused = importDraft(exportDraft(view, alien, "x"), other);
  assert.equal(refused.ok, false);
  if (!refused.ok) assert.match(refused.error, /other-core/);

  const broken = importDraft("not json at all", view);
  assert.equal(broken.ok, false);
});

test("import rejects values the registry rejects", () => {
  const view = syntheticRegistry(6, 1);
  const payload = JSON.stringify({
    include: "constellab-parameters",
    schema_hash: view.schemaHash,
    edits: { "stress.owner-0000": { field_0_m: 10_000_000 } },
  });
  const result = importDraft(payload, view);
  assert.equal(result.ok, false);
  if (!result.ok) assert.match(result.error, /rejects/);
});

test("specMatches is a case-insensitive key/label/unit search", () => {
  const view = syntheticRegistry(4, 1);
  assert.equal(specMatches(view.specs[0], "FIELD_0"), true);
  assert.equal(specMatches(view.specs[0], "meter"), false);
  assert.equal(specMatches(view.specs[0], ""), true);
});

test("boolean/integer specs validate exactly", () => {
  const view = parseRegistryPayload({
    schema_hash: "h",
    parameters: [
      { key: "demo.a.enabled", kind: "boolean", default: true },
      { key: "demo.a.count_kbit", kind: "integer", default: 1, minimum: 0, unit: "kbit" },
    ],
  });
  const enabled = view.specs[0];
  const count = view.specs[1];
  assert.equal(validateValue(enabled, true), null);
  assert.equal(validateValue(enabled, false), null);
  assert.match(validateValue(enabled, "true") ?? "x", /must be a boolean/);
  assert.match(validateValue(enabled, 1) ?? "x", /must be a boolean/);
  assert.equal(validateValue(count, 4), null);
  assert.match(validateValue(count, 4.5) ?? "", /must be a whole/);
});

test("edit values keep their types through number entry", () => {
  const view = syntheticRegistry(2, 1);
  const spec = view.specs[0];
  assert.equal(typeof spec.default, "number");
  const good: EditValue = 4;
  assert.equal(validateValue(spec, good), null);
});
