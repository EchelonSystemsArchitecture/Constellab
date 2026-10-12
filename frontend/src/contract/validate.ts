/**
 * Minimal JSON Schema validator for the contract subset.
 *
 * Twin of core/constellab_core/validation.py: same keywords, same error paths,
 * same messages where practical. Both are contract-tested against the fixtures
 * in core/tests/fixtures. Unsupported keywords throw so a schema change can
 * never be silently ignored.
 */

export interface ValidationIssue {
  path: string;
  message: string;
}

type Json = null | boolean | number | string | Json[] | { [key: string]: Json };
type SchemaNode = Record<string, unknown>;

const SUPPORTED_KEYWORDS = new Set([
  "$schema", "$id", "$ref", "$defs", "title", "description", "default", "x-schema-version",
  "type", "required", "properties", "additionalProperties", "enum", "const",
  "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum",
  "minLength", "maxLength", "pattern", "minItems", "maxItems", "items", "x-unique-by",
]);

export class UnsupportedSchema extends Error {}

function typeOf(value: unknown): string {
  if (value === null) return "null";
  if (Array.isArray(value)) return "array";
  if (typeof value === "number") return Number.isInteger(value) ? "integer" : "number";
  if (typeof value === "object") return "object";
  if (typeof value === "string" || typeof value === "boolean") return typeof value;
  throw new TypeError(`unsupported value: ${typeof value}`);
}

function matchesType(value: unknown, expected: string): boolean {
  const actual = typeOf(value);
  if (expected === "number") return actual === "number" || actual === "integer";
  return actual === expected;
}

export class SchemaValidator {
  constructor(private readonly root: SchemaNode) {
    this.checkSupported(root);
  }

  private checkSupported(node: SchemaNode): void {
    for (const [key, child] of Object.entries(node)) {
      if (key === "properties" || key === "$defs") {
        for (const sub of Object.values(child as Record<string, SchemaNode>)) this.checkSupported(sub);
      } else if (key === "items") {
        this.checkSupported(child as SchemaNode);
      } else if (!SUPPORTED_KEYWORDS.has(key)) {
        throw new UnsupportedSchema(`unsupported schema keyword: ${key}`);
      }
    }
  }

  resolve(ref: string): SchemaNode {
    if (!ref.startsWith("#/")) throw new UnsupportedSchema(`only local $ref is supported, got ${ref}`);
    let node: unknown = this.root;
    for (const part of ref.slice(2).split("/")) node = (node as Record<string, unknown>)[part];
    return node as SchemaNode;
  }

  validate(instance: unknown, ref: string): ValidationIssue[] {
    const errors: ValidationIssue[] = [];
    this.walk(instance, this.resolve(ref), "$", errors);
    return errors;
  }

  private walk(value: unknown, schema: SchemaNode, path: string, errors: ValidationIssue[]): void {
    if (typeof schema.$ref === "string") {
      const { $ref, ...rest } = schema;
      this.walk(value, { ...this.resolve($ref), ...rest }, path, errors);
      return;
    }
    const expected = schema.type as string | undefined;
    if (expected !== undefined && !matchesType(value, expected)) {
      errors.push({ path, message: `must be ${expected}, got ${typeOf(value)}` });
      return;
    }
    if ("const" in schema && value !== schema.const) errors.push({ path, message: `must equal ${JSON.stringify(schema.const)}` });
    if (Array.isArray(schema.enum) && !schema.enum.includes(value as Json)) {
      errors.push({ path, message: `must be one of ${JSON.stringify(schema.enum)}` });
    }

    if (typeof value === "number") {
      if (typeof schema.minimum === "number" && value < schema.minimum) errors.push({ path, message: `must be >= ${schema.minimum}` });
      if (typeof schema.maximum === "number" && value > schema.maximum) errors.push({ path, message: `must be <= ${schema.maximum}` });
      if (typeof schema.exclusiveMinimum === "number" && value <= schema.exclusiveMinimum) errors.push({ path, message: `must be > ${schema.exclusiveMinimum}` });
      if (typeof schema.exclusiveMaximum === "number" && value >= schema.exclusiveMaximum) errors.push({ path, message: `must be < ${schema.exclusiveMaximum}` });
    }

    if (typeof value === "string") {
      if (typeof schema.minLength === "number" && value.length < schema.minLength) errors.push({ path, message: `must have at least ${schema.minLength} characters` });
      if (typeof schema.maxLength === "number" && value.length > schema.maxLength) errors.push({ path, message: `must have at most ${schema.maxLength} characters` });
      if (typeof schema.pattern === "string" && !new RegExp(schema.pattern).test(value)) errors.push({ path, message: `must match pattern ${schema.pattern}` });
    }

    if (Array.isArray(value)) {
      if (typeof schema.minItems === "number" && value.length < schema.minItems) errors.push({ path, message: `must have at least ${schema.minItems} items` });
      if (typeof schema.maxItems === "number" && value.length > schema.maxItems) errors.push({ path, message: `must have at most ${schema.maxItems} items` });
      if (schema.items) value.forEach((item, index) => this.walk(item, schema.items as SchemaNode, `${path}[${index}]`, errors));
      if (typeof schema["x-unique-by"] === "string") {
        const key = schema["x-unique-by"];
        const seen = new Map<unknown, number>();
        value.forEach((item, index) => {
          if (item && typeof item === "object" && !Array.isArray(item) && key in item) {
            const ident = (item as Record<string, unknown>)[key];
            const first = seen.get(ident);
            if (first !== undefined) {
              errors.push({ path: `${path}[${index}].${key}`, message: `duplicate ${key} ${JSON.stringify(ident)} (first seen at ${path}[${first}])` });
            } else {
              seen.set(ident, index);
            }
          }
        });
      }
    }

    if (value !== null && typeof value === "object" && !Array.isArray(value)) {
      const record = value as Record<string, unknown>;
      const properties = (schema.properties ?? {}) as Record<string, SchemaNode>;
      for (const name of (schema.required ?? []) as string[]) {
        if (!(name in record)) errors.push({ path: `${path}.${name}`, message: "missing required field" });
      }
      for (const [name, child] of Object.entries(record)) {
        if (name in properties) this.walk(child, properties[name], `${path}.${name}`, errors);
        else if (schema.additionalProperties === false) errors.push({ path: `${path}.${name}`, message: "unknown field" });
      }
    }
  }
}
