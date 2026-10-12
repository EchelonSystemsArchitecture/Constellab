/**
 * Renderer-side entry to the simulation/visualization contract.
 *
 * The frontend never computes orbital state. It parses snapshots produced by
 * the core, rejects anything that is malformed or from an incompatible schema
 * version, and hands typed data to the scene. Rendered objects (meshes, lines,
 * labels) are a separate concern built from these types, never stored in them.
 */
import {
  DefinitionName,
  SCHEMA_VERSION,
  SIMULATION_CONTRACT_SCHEMA,
  SimulationConfig,
  SimulationSnapshot,
} from "./generated";
import { SchemaValidator, ValidationIssue } from "./validate";

export * from "./generated";
export { SchemaValidator, UnsupportedSchema } from "./validate";
export type { ValidationIssue } from "./validate";

export const validator = new SchemaValidator(SIMULATION_CONTRACT_SCHEMA as unknown as Record<string, unknown>);

export class ContractError extends Error {
  constructor(public readonly errors: ValidationIssue[]) {
    super("contract violation: " + errors.map((e) => `${e.path}: ${e.message}`).join("; "));
    this.name = "ContractError";
  }
}

export function parseVersion(version: string): [number, number, number] {
  const match = /^(\d+)\.(\d+)\.(\d+)$/.exec(version);
  if (!match) throw new RangeError(`not a semantic version: ${version}`);
  return [Number(match[1]), Number(match[2]), Number(match[3])];
}

/** Same major as the schema we were built against and a minor that is not newer. */
export function isCompatibleVersion(version: unknown): boolean {
  if (typeof version !== "string") return false;
  try {
    const [major, minor] = parseVersion(version);
    const [ourMajor, ourMinor] = parseVersion(SCHEMA_VERSION);
    return major === ourMajor && minor <= ourMinor;
  } catch {
    return false;
  }
}

function versionIssues(payload: unknown): ValidationIssue[] {
  if (!payload || typeof payload !== "object" || !("schema_version" in payload)) return [];
  const version = (payload as { schema_version: unknown }).schema_version;
  if (isCompatibleVersion(version)) return [];
  return [{
    path: "$.schema_version",
    message: `incompatible schema version ${JSON.stringify(version)}; this renderer supports ${SCHEMA_VERSION}`,
  }];
}

export function validatePayload(payload: unknown, definition: DefinitionName): ValidationIssue[] {
  const version = versionIssues(payload);
  return version.length > 0 ? version : validator.validate(payload, `#/$defs/${definition}`);
}

function parse<T>(payload: unknown, definition: DefinitionName): T {
  const errors = validatePayload(payload, definition);
  if (errors.length > 0) throw new ContractError(errors);
  return payload as T;
}

export const parseSnapshot = (payload: unknown): SimulationSnapshot => parse<SimulationSnapshot>(payload, "SimulationSnapshot");
export const parseConfig = (payload: unknown): SimulationConfig => parse<SimulationConfig>(payload, "SimulationConfig");
