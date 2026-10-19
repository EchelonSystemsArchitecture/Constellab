/**
 * Day 8: scenario catalog + validated runtime load.
 *
 * The core validates every configuration; this client only transports it and
 * surfaces the core's field-path diagnostics unchanged.
 */
import { parseConfig, type SimulationConfig, type SimulationClock } from "../contract";

export const CORE_URL = "http://127.0.0.1:8765";

export interface ScenarioSummary {
  key: string;
  scenario_id: string;
  name: string;
  satellites: number;
  epoch_utc: string;
  time_scale: number;
}

export interface LoadedScenario {
  scenario: SimulationConfig;
  clock: SimulationClock;
  source: string;
}

export class CoreError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly errors: { path: string; message: string }[] = [],
  ) {
    super(message);
    this.name = "CoreError";
  }
}

async function readJson(res: Response): Promise<unknown> {
  const text = await res.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    throw new CoreError(`core returned non-JSON response (HTTP ${res.status})`, res.status);
  }
}

function errorFrom(payload: unknown, status: number, fallback: string): CoreError {
  if (payload && typeof payload === "object") {
    const p = payload as { error?: string; message?: string; errors?: { path: string; message: string }[] };
    const detail = p.errors?.[0] ? `${p.errors[0].path}: ${p.errors[0].message}` : p.message;
    return new CoreError(detail ?? p.error ?? fallback, status, p.errors ?? []);
  }
  return new CoreError(fallback, status);
}

export async function listScenarios(): Promise<{ scenarios: ScenarioSummary[]; active: string | null }> {
  const res = await fetch(`${CORE_URL}/api/scenarios`);
  const payload = await readJson(res);
  if (!res.ok) throw errorFrom(payload, res.status, `core returned HTTP ${res.status}`);
  const { scenarios, active } = payload as { scenarios: ScenarioSummary[]; active: string | null };
  if (!Array.isArray(scenarios)) throw new CoreError("scenario catalog is malformed", res.status);
  return { scenarios, active };
}

/** Load a built-in scenario by key; the core restarts its clock at t=0. */
export async function loadScenario(key: string): Promise<LoadedScenario> {
  const res = await fetch(`${CORE_URL}/api/scenario`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ key }),
  });
  const payload = await readJson(res);
  if (!res.ok) throw errorFrom(payload, res.status, `core rejected scenario '${key}'`);
  const data = payload as { scenario: unknown; clock: SimulationClock; source: string };
  return {
    scenario: parseConfig(data.scenario),
    clock: data.clock,
    source: data.source,
  };
}

/** Submit an inline configuration through the same validated load transaction. */
export async function loadConfig(config: SimulationConfig): Promise<LoadedScenario> {
  const res = await fetch(`${CORE_URL}/api/scenario`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ config }),
  });
  const payload = await readJson(res);
  if (!res.ok) throw errorFrom(payload, res.status, "core rejected the configuration");
  const data = payload as { scenario: unknown; clock: SimulationClock; source: string };
  return {
    scenario: parseConfig(data.scenario),
    clock: data.clock,
    source: data.source,
  };
}
