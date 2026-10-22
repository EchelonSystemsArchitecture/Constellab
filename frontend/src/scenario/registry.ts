/**
 * Day 22: thousands-of-fields parameter editing.
 *
 * The Day 19 core registry is data; this module is its client mirror. All the
 * interactive machinery — parsing the `/api/registry` payload, search, owner
 * filtering, the edited-only view, pagination (no virtualization library: a
 * bounded page render keeps 10,000 fields from becoming 10,000 components),
 * local type/bounds validation with a field-path summary, and versioned
 * export/import — is pure here, so the pagination and validation maths are
 * exercised headlessly and the component stays a thin shell.
 *
 * Edits are a draft: they never touch the running scenario until they are
 * applied, and they survive filter changes, page switches and validation
 * errors because validation never discards a value.
 */

export interface ParameterSpecView {
  key: string;
  owner: string;
  shortKey: string;
  kind: "number" | "integer" | "boolean" | "string";
  label: string;
  unit: string;
  unitSlug: string;
  minimum: number | null;
  maximum: number | null;
  options: (number | string | boolean)[] | null;
  default: number | string | boolean;
  distribution: string;
  mutability: string;
  modelVisible: boolean;
  updateCadenceS: number | null;
  schemaVersion: number;
  description: string;
}

export interface RegistryView {
  schemaVersion: number;
  schemaHash: string;
  specs: ParameterSpecView[];
  owners: string[];
}

/** Valid edit value: whatever a spec may carry. */
export type EditValue = number | string | boolean;

export type EditMap = Record<string /* owner */, Record<string /* shortKey */, EditValue>>;

export interface ValidationIssue {
  path: string;
  message: string;
}

const KINDS = new Set(["number", "integer", "boolean", "string"]);

export class RegistryError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "RegistryError";
  }
}

/** Parse the core's registry payload; unknown shapes are rejected, not guessed. */
export function parseRegistryPayload(payload: unknown): RegistryView {
  if (!payload || typeof payload !== "object") {
    throw new RegistryError("registry payload must be an object");
  }
  const p = payload as {
    schema_version?: unknown;
    schema_hash?: unknown;
    owners?: unknown;
    parameters?: unknown;
  };
  if (typeof p.schema_hash !== "string") {
    throw new RegistryError("registry payload is missing its schema_hash");
  }
  const rawSpecs = p.parameters;
  if (!Array.isArray(rawSpecs)) {
    throw new RegistryError("registry payload must carry a parameters list");
  }
  const specs: ParameterSpecView[] = rawSpecs.map((entry, index) => {
    if (!entry || typeof entry !== "object") {
      throw new RegistryError(`parameter ${index} must be an object`);
    }
    const s = entry as Record<string, unknown>;
    const key = typeof s.key === "string" ? s.key : null;
    if (!key) throw new RegistryError(`parameter ${index} is missing a key`);
    const owner = typeof s.owner === "string" ? s.owner : key.split(".").slice(0, -1).join(".");
    const kind = typeof s.kind === "string" && KINDS.has(s.kind) ? s.kind : "number";
    if (kind === "number" || kind === "integer") {
      if (s.default === undefined) throw new RegistryError(`${key} is missing a default`);
      if (typeof s.default !== "number") throw new RegistryError(`${key}: numeric default required`);
    } else if (typeof s.default !== "number" && typeof s.default !== "string" && typeof s.default !== "boolean") {
      throw new RegistryError(`${key}: non-numeric default must be a scalar`);
    }
    const options = Array.isArray(s.enum) ? (s.enum as (number | string | boolean)[]) : null;
    return {
      key,
      owner,
      shortKey: key.startsWith(`${owner}.`) ? key.slice(owner.length + 1) : key,
      kind: kind as ParameterSpecView["kind"],
      label: typeof s.label === "string" ? s.label : key,
      unit: typeof s.unit === "string" ? s.unit : "1",
      unitSlug: typeof s.unit_slug === "string" ? s.unit_slug : "",
      minimum: typeof s.minimum === "number" ? s.minimum : null,
      maximum: typeof s.maximum === "number" ? s.maximum : null,
      options: options && options.length ? options : null,
      default: s.default as EditValue,
      distribution: typeof s.distribution === "string" ? s.distribution : "constant",
      mutability: typeof s.mutability === "string" ? s.mutability : "static",
      modelVisible: s.model_visible !== false,
      updateCadenceS: typeof s.update_cadence_s === "number" ? s.update_cadence_s : null,
      schemaVersion: typeof s.schema_version === "number" ? s.schema_version : 1,
      description: typeof s.description === "string" ? s.description : "",
    };
  });
  const owners = [...new Set(specs.map((s) => s.owner))].sort();
  return {
    schemaVersion: typeof p.schema_version === "number" ? p.schema_version : 1,
    schemaHash: p.schema_hash,
    specs,
    owners,
  };
}

/** A tiny helper so tests can build a 10,000-field synthetic registry cheaply. */
export function syntheticRegistry(count: number, owners = 4): RegistryView {
  const specs: ParameterSpecView[] = [];
  for (let index = 0; index < count; index++) {
    const owner = `stress.owner-${(index % owners).toString().padStart(4, "0")}`;
    const unit = (["m", "W", "J", "s"] as const)[index % 4];
    const kind = (["number", "integer", "number", "number"] as const)[index % 4];
    specs.push({
      key: `${owner}.field_${index}_${unit}`,
      owner,
      shortKey: `field_${index}_${unit}`,
      kind,
      label: `Stress field ${index}`,
      unit,
      unitSlug: unit,
      minimum: 0,
      maximum: index * 10 + 10,
      options: null,
      default: (index % 9) + 1,
      distribution: (["constant", "uniform", "normal", "log-uniform"] as const)[index % 4],
      mutability: index % 2 === 0 ? "static" : "run",
      modelVisible: index % 4 !== 3,
      updateCadenceS: 10 + (index % 5),
      schemaVersion: 1,
      description: "Synthetic stress field.",
    });
  }
  return {
    schemaVersion: 1,
    schemaHash: `synthetic-${count}`,
    specs,
    owners: [...new Set(specs.map((s) => s.owner))].sort(),
  };
}

export interface RegistryFilterState {
  query: string;
  owner: string | null;
  editedOnly: boolean;
  page: number;
  pageSize: number;
}

/** Case-insensitive query match over key, label and unit. */
export function specMatches(spec: ParameterSpecView, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  return `${spec.key} ${spec.label} ${spec.unit}`.toLowerCase().includes(q);
}

export interface PageResult {
  total: number;
  pageCount: number;
  page: number;
  slice: ParameterSpecView[];
  /** True when at least one spec was touched and hidden by the current view. */
  hiddenEdits: number;
}

/** Filter + paginate. Never re-renders more than pageSize rows. */
export function paginateSpecs(
  specs: ParameterSpecView[],
  filter: RegistryFilterState,
  editedKeys: ReadonlySet<string>,
): PageResult {
  let matched = 0;
  let firstVisible: number[] = [];
  for (let index = 0; index < specs.length; index++) {
    const spec = specs[index];
    if (filter.owner && spec.owner !== filter.owner) continue;
    if (!specMatches(spec, filter.query)) continue;
    if (filter.editedOnly && !editedKeys.has(spec.key)) continue;
    matched += 1;
    firstVisible.push(index);
  }
  const pageCount = Math.max(1, Math.ceil(matched / filter.pageSize));
  const page = Math.min(Math.max(1, filter.page), pageCount);
  const start = (page - 1) * filter.pageSize;
  const slice = firstVisible.slice(start, start + filter.pageSize).map((i) => specs[i]);
  // How many edited fields the current view hides (search/owner/other page).
  let hiddenEdits = 0;
  for (const key of editedKeys) {
    const spec = specs.find((s) => s.key === key);
    if (!spec) continue;
    if (filter.editedOnly) continue; // the edited-only view shows them all
    if (filter.owner && spec.owner !== filter.owner) hiddenEdits += 1;
    else if (!specMatches(spec, filter.query)) hiddenEdits += 1;
  }
  return { total: matched, pageCount, page, slice, hiddenEdits };
}

/** Validate one value against its spec: type, bounds and enum membership. */
export function validateValue(spec: ParameterSpecView, value: unknown): string | null {
  if (value === null || value === undefined) {
    return `a value is required for ${spec.key}`;
  }
  if (spec.kind === "number" || spec.kind === "integer") {
    if (typeof value !== "number" || !Number.isFinite(value)) {
      if (typeof value === "boolean") return `${spec.key}: must be a ${spec.kind}`;
      return `${spec.key}: must be a ${spec.kind}${spec.unit !== "1" ? ` in ${spec.unit}` : ""}`;
    }
    if (spec.kind === "integer" && !Number.isInteger(value)) {
      return `${spec.key}: must be a whole ${spec.unit !== "1" ? `value in ${spec.unit}` : "number"}`;
    }
    if (spec.minimum !== null && value < spec.minimum) {
      return `${spec.key}: must be >= ${spec.minimum} ${spec.unit}`;
    }
    if (spec.maximum !== null && value > spec.maximum) {
      return `${spec.key}: must be <= ${spec.maximum} ${spec.unit}`;
    }
    return null;
  }
  if (spec.options) {
    const ok = spec.options.some((option) => `${option}` === `${value}`);
    return ok ? null : `${spec.key}: must be one of ${spec.options.join(", ")}`;
  }
  if (spec.kind === "boolean") {
    return typeof value === "boolean" ? null : `${spec.key}: must be a boolean`;
  }
  if (spec.kind === "string") {
    return typeof value === "string" ? null : `${spec.key}: must be a string`;
  }
  return null;
}

/** Validate the whole draft; returns every field-path issue (none swallowed). */
export function validateEdits(view: RegistryView, edits: EditMap): ValidationIssue[] {
  const byKey = new Map(view.specs.map((s) => [s.key, s] as const));
  const issues: ValidationIssue[] = [];
  for (const [owner, values] of Object.entries(edits)) {
    for (const [shortKey, value] of Object.entries(values)) {
      const spec = byKey.get(`${owner}.${shortKey}`);
      if (!spec) {
        issues.push({
          path: `${owner}.${shortKey}`,
          message: "no registered parameter consumes this key; it would not change behaviour",
        });
        continue;
      }
      const problem = validateValue(spec, value);
      if (problem) issues.push({ path: `${owner}.${shortKey}`, message: problem });
    }
  }
  return issues.sort((a, b) => a.path.localeCompare(b.path));
}

/** Merge typed defaults with the draft (what a validated apply would use). */
export function effectiveEdits(view: RegistryView, edits: EditMap): EditMap {
  const out: EditMap = {};
  for (const spec of view.specs) {
    (out[spec.owner] ??= {})[spec.shortKey] = spec.default as EditValue;
  }
  for (const [owner, values] of Object.entries(edits)) {
    out[owner] ??= {};
    Object.assign(out[owner], values);
  }
  return out;
}

/** Versioned export: the registry identity travels with the values. */
export function exportDraft(view: RegistryView, edits: EditMap, baseUrl: string): string {
  return JSON.stringify(
    {
      include: "constellab-parameters",
      schema_version: view.schemaVersion,
      schema_hash: view.schemaHash,
      exported_from: baseUrl,
      edits,
    },
    null,
    2,
  );
}

export type ImportResult =
  | { ok: true; edits: EditMap; schemaHash: string; imported: number }
  | { ok: false; error: string };

/** Import a draft file; a schema-hash mismatch is refused, not silently merged. */
export function importDraft(text: string, view: RegistryView): ImportResult {
  let payload: unknown;
  try {
    payload = JSON.parse(text);
  } catch (err) {
    return { ok: false, error: `not valid JSON: ${err instanceof Error ? err.message : String(err)}` };
  }
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    return { ok: false, error: "a parameter draft must be an object" };
  }
  const p = payload as Record<string, unknown>;
  if (p.include !== "constellab-parameters") {
    return { ok: false, error: 'missing "include": "constellab-parameters"' };
  }
  if (p.schema_hash !== view.schemaHash) {
    return {
      ok: false,
      error: `draft was exported against schema ${p.schema_hash as string}, this core runs ${view.schemaHash}`,
    };
  }
  if (!p.edits || typeof p.edits !== "object") {
    return { ok: false, error: "draft is missing its edits" };
  }
  const edits = p.edits as EditMap;
  let imported = 0;
  for (const values of Object.values(edits)) {
    imported += Object.keys(values ?? {}).length;
  }
  if (validateEdits(view, edits).length) {
    return { ok: false, error: "draft contains values this registry rejects" };
  }
  return { ok: true, edits, schemaHash: view.schemaHash, imported };
}

/** Human formatting: units and integer-ness come from the spec metadata. */
export function formatValue(spec: ParameterSpecView, value: EditValue | undefined): string {
  if (value === undefined) {
    return `${spec.default}${spec.unit !== "1" ? ` ${spec.unit}` : ""}`;
  }
  if (typeof value === "number" && spec.kind === "number") {
    return `${new Intl.NumberFormat("en-US", { maximumFractionDigits: 6 }).format(value)}${spec.unit !== "1" ? ` ${spec.unit}` : ""}`;
  }
  return `${value}`;
}
