/**
 * Day 9: derive editor fields from the contract schema.
 *
 * There is no per-parameter code here: labels, units, steps and bounds all come
 * from `SIMULATION_CONTRACT_SCHEMA` (including its `x-ui` annotations), and the
 * same schema validator that checks snapshots validates drafts before apply.
 */
import {
  SIMULATION_CONTRACT_SCHEMA,
  validatePayload,
  type SimulationConfig,
  type ValidationIssue,
} from "../contract";

type JsonSchema = Record<string, unknown>;

export type EditableDefinition = "SimulationConfig" | "SatelliteConfig" | "OrbitElements";

export type FieldType = "number" | "integer" | "string" | "boolean" | "unsupported";
export type WidgetKind = FieldType | "readonly";

export interface UiAnnotation {
  label?: string;
  unit?: string;
  step?: number;
  readOnly?: boolean;
}

export interface FieldSpec {
  definition: EditableDefinition;
  key: string;
  /** Draft path, e.g. `time_scale` or `satellites[0].orbit.eccentricity`. */
  path: string;
  label: string;
  description?: string;
  type: FieldType;
  widget: WidgetKind;
  unit?: string;
  step?: number;
  minimum?: number;
  maximum?: number;
  exclusiveMinimum?: number;
  exclusiveMaximum?: number;
  enumValues?: unknown[];
  readOnly: boolean;
  required: boolean;
  defaultValue?: unknown;
}

const ROOT = SIMULATION_CONTRACT_SCHEMA as unknown as JsonSchema;
const DEFS = (ROOT.$defs ?? {}) as Record<string, JsonSchema>;
const UI = (ROOT["x-ui"] ?? {}) as Record<string, UiAnnotation>;

export function definitionSchema(definition: EditableDefinition): JsonSchema {
  const node = DEFS[definition];
  if (!node) throw new Error(`unknown contract definition: ${definition}`);
  return node;
}

function resolve(node: JsonSchema): JsonSchema {
  const ref = node.$ref;
  if (typeof ref !== "string") return node;
  const name = ref.split("/").pop() ?? "";
  const resolved = DEFS[name];
  if (!resolved) throw new Error(`unresolvable schema $ref: ${ref}`);
  return resolved;
}

function prettify(key: string): string {
  return key
    .replace(/_deg$/, "")
    .replace(/_km_s$/, " (km/s)")
    .replace(/_km$/, " (km)")
    .replace(/_/g, " ")
    .toUpperCase();
}

function fieldType(node: JsonSchema): FieldType {
  const type = node.type;
  if (type === "number" || type === "integer" || type === "string" || type === "boolean") return type;
  return "unsupported";
}

export function widgetKind(field: FieldSpec): WidgetKind {
  if (field.readOnly) return "readonly";
  if (field.type === "unsupported") return "unsupported";
  return field.type;
}

/**
 * Fields of one definition, in schema order.
 *
 * `pathPrefix` lets the same OrbitElements definition be edited in place inside
 * a configured satellite (`satellites[2].orbit.eccentricity`).
 */
export function definitionFields(
  definition: EditableDefinition,
  options: { pathPrefix?: string; required?: boolean } = {},
): FieldSpec[] {
  const schema = definitionSchema(definition);
  const properties = (schema.properties ?? {}) as Record<string, JsonSchema>;
  const required = new Set<string>((schema.required as string[] | undefined) ?? []);
  const prefix = options.pathPrefix;

  return Object.entries(properties).map(([key, raw]) => {
    const node = resolve(raw);
    const ui = UI[`${definition}.${key}`] ?? {};
    const type = fieldType(node);
    const base: FieldSpec = {
      definition,
      key,
      path: prefix ? `${prefix}.${key}` : key,
      label: ui.label ?? prettify(key),
      description: typeof node.description === "string" ? node.description : undefined,
      type,
      widget: "unsupported",
      readOnly: ui.readOnly === true,
      required: required.has(key),
    };
    if (ui.unit !== undefined) base.unit = ui.unit;
    if (ui.step !== undefined) base.step = ui.step;
    if (typeof node.minimum === "number") base.minimum = node.minimum;
    if (typeof node.maximum === "number") base.maximum = node.maximum;
    if (typeof node.exclusiveMinimum === "number") base.exclusiveMinimum = node.exclusiveMinimum;
    if (typeof node.exclusiveMaximum === "number") base.exclusiveMaximum = node.exclusiveMaximum;
    if (Array.isArray(node.enum)) base.enumValues = node.enum;
    if (node.default !== undefined) base.defaultValue = node.default;
    base.widget = widgetKind(base);
    return base;
  });
}

/** Path segments for `satellites[3].orbit.raan_deg`. */
export function pathSegments(path: string): (string | number)[] {
  const segments: (string | number)[] = [];
  const pattern = /([^.[\]]+)|\[(\d+)\]/g;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(path)) !== null) {
    segments.push(match[1] !== undefined ? match[1] : Number(match[2]));
  }
  return segments;
}

export function getAtPath(root: unknown, path: string): unknown {
  let node: unknown = root;
  for (const segment of pathSegments(path)) {
    if (node === null || typeof node !== "object") return undefined;
    node = (node as Record<string | number, unknown>)[segment];
  }
  return node;
}

/** Immutable draft update; the running scenario object is never touched. */
export function updateAtPath<T>(root: T, path: string, value: unknown): T {
  const clone = JSON.parse(JSON.stringify(root)) as unknown;
  const segments = pathSegments(path);
  let node = clone as Record<string | number, unknown>;
  for (let i = 0; i < segments.length - 1; i++) {
    const next = node[segments[i]];
    if (next === null || typeof next !== "object") {
      throw new Error(`cannot write ${path}: ${segments.slice(0, i + 1).join(".")} is not an object`);
    }
    node = next as Record<string | number, unknown>;
  }
  node[segments[segments.length - 1]] = value;
  return clone as T;
}

/** Schema default for a definition/key, when the schema declares one. */
export function schemaDefault(definition: EditableDefinition, key: string): unknown {
  const properties = (definitionSchema(definition).properties ?? {}) as Record<string, JsonSchema>;
  return resolve(properties[key] ?? {}).default;
}

/** Validate a draft config with the contract validator (same errors as the core). */
export function validateDraft(draft: SimulationConfig): ValidationIssue[] {
  return validatePayload(draft, "SimulationConfig");
}

/** Index validation issues by draft field path (drops the leading `$.`). */
export function issuesByPath(issues: ValidationIssue[]): Map<string, string[]> {
  const map = new Map<string, string[]>();
  for (const issue of issues) {
    const path = issue.path.replace(/^\$\.?/, "");
    const list = map.get(path) ?? [];
    list.push(issue.message);
    map.set(path, list);
  }
  return map;
}

/** Issues that belong to a field or any of its descendants. */
export function issuesForField(index: Map<string, string[]>, path: string): string[] {
  const exact = index.get(path) ?? [];
  const nested: string[] = [];
  for (const [key, messages] of index) {
    if (key.startsWith(`${path}[`) || key.startsWith(`${path}.`)) nested.push(...messages);
  }
  return [...exact, ...nested];
}
