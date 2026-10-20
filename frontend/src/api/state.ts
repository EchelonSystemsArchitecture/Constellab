/**
 * Day 10: client side of the canonical state stream.
 *
 * The core stamps every reply with a monotonic revision. Polling can deliver a
 * late reply after a newer one (a paused tab, a slow request, a scenario load),
 * so the renderer accepts a state only when it is not older than what it already
 * shows. This module keeps that rule pure and testable, with no React or fetch.
 */
import { ContractError, parseSnapshot, type SimulationSnapshot } from "../contract";

export interface StateEnvelope {
  /** Id echoed by the core for the request that produced this state. */
  requestId: string;
  /** Monotonic state revision; higher is newer. */
  revision: number;
  scenarioId: string;
  snapshot: SimulationSnapshot;
}

export interface StateCursor {
  revision: number;
  scenarioId: string;
  simulationTimeS: number;
}

export function cursorOf(state: StateEnvelope | StateCursor): StateCursor {
  if ("snapshot" in state) {
    return {
      revision: state.revision,
      scenarioId: state.scenarioId,
      simulationTimeS: state.snapshot.clock.simulation_time_s,
    };
  }
  return state;
}

/**
 * True when `next` may replace `previous`.
 *
 * A newer revision always wins. An equal revision is only the same state (or a
 * scenario load that did not bump further), so it is accepted when its clock is
 * not behind. An older revision is stale and must never roll the UI backward.
 */
export function shouldAcceptState(previous: StateCursor | null, next: StateEnvelope): boolean {
  if (previous === null) return true;
  const candidate = cursorOf(next);
  if (candidate.revision > previous.revision) return true;
  if (candidate.revision < previous.revision) return false;
  if (candidate.scenarioId !== previous.scenarioId) return false;
  return candidate.simulationTimeS >= previous.simulationTimeS;
}

function envelopeError(message: string): ContractError {
  return new ContractError([{ path: "$.revision", message }]);
}

/**
 * Validate the `/api/state` envelope and its embedded contract snapshot.
 * A malformed envelope is a contract violation, never a silent fallback.
 */
export function parseStateEnvelope(payload: unknown): StateEnvelope {
  if (!payload || typeof payload !== "object") throw envelopeError("state payload is not an object");
  const raw = payload as Record<string, unknown>;
  const { request_id: requestId, revision, scenario_id: scenarioId, snapshot } = raw;
  if (typeof requestId !== "string" || requestId.length === 0) {
    throw envelopeError("request_id must be a non-empty string");
  }
  if (typeof revision !== "number" || !Number.isInteger(revision) || revision < 1) {
    throw envelopeError("revision must be a positive integer");
  }
  if (typeof scenarioId !== "string" || scenarioId.length === 0) {
    throw envelopeError("scenario_id must be a non-empty string");
  }
  const parsed = parseSnapshot(snapshot);
  if (parsed.scenario_id !== scenarioId) {
    throw envelopeError(`envelope scenario_id ${scenarioId} does not match snapshot ${parsed.scenario_id}`);
  }
  return { requestId, revision, scenarioId, snapshot: parsed };
}
