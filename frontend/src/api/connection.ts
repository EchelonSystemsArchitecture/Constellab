/**
 * Day 12: connection state for the local core.
 *
 * The renderer keeps polling, but it must tell the truth about *why* a frame is
 * frozen instead of showing a stale globe as if it were live. This module is a
 * pure reducer so the backoff and recovery rules are testable without a browser.
 *
 * A restarted core starts its revision counter from zero; `reconnectResetsCursor`
 * says when the client must forget the old revision cursor so a fresh core can be
 * accepted instead of having every reply dropped as "older".
 */
import { SCENE_CONFIG } from "../scene/config";

export type ConnectionPhase = "connecting" | "live" | "degraded" | "down" | "invalid";

export interface ConnectionPolicy {
  baseDelayMs: number;
  maxDelayMs: number;
}

export interface ConnectionInfo {
  phase: ConnectionPhase;
  /** Consecutive failed requests since the last success. */
  attempts: number;
  lastOkAtMs: number | null;
  lastError: string | null;
  retryAtMs: number | null;
  retryDelayMs: number;
}

export type ConnectionEvent =
  | { type: "ok"; atMs: number }
  | { type: "failure"; atMs: number; message: string }
  | { type: "invalid"; atMs: number; message: string };

const DEFAULT_POLICY: ConnectionPolicy = {
  baseDelayMs: SCENE_CONFIG.connection.baseDelayMs,
  maxDelayMs: SCENE_CONFIG.connection.maxDelayMs,
};

/** Exponential backoff: base, 2×base, 4×base … capped at `maxDelayMs`. */
export function retryDelayMs(attempts: number, policy: ConnectionPolicy = DEFAULT_POLICY): number {
  if (!Number.isFinite(attempts) || attempts <= 0) return 0;
  return Math.min(policy.maxDelayMs, policy.baseDelayMs * 2 ** (attempts - 1));
}

export function initialConnection(phase: ConnectionPhase = "connecting"): ConnectionInfo {
  return {
    phase,
    attempts: 0,
    lastOkAtMs: null,
    lastError: null,
    retryAtMs: null,
    retryDelayMs: 0,
  };
}

export function nextConnection(
  previous: ConnectionInfo,
  event: ConnectionEvent,
  policy: ConnectionPolicy = DEFAULT_POLICY,
): ConnectionInfo {
  if (event.type === "ok") {
    return {
      phase: "live",
      attempts: 0,
      lastOkAtMs: event.atMs,
      lastError: null,
      retryAtMs: null,
      retryDelayMs: 0,
    };
  }
  const attempts = previous.attempts + 1;
  const delay = retryDelayMs(attempts, policy);
  const phase: ConnectionPhase = event.type === "invalid"
    ? "invalid"
    // One delayed reply after a good history is reported as degraded: the scene
    // on screen is still the last true state, just older than the poll cadence.
    : previous.lastOkAtMs !== null && attempts === 1
      ? "degraded"
      : "down";
  return {
    phase,
    attempts,
    lastOkAtMs: previous.lastOkAtMs,
    lastError: event.message,
    retryAtMs: event.atMs + delay,
    retryDelayMs: delay,
  };
}

/** True when this success follows a broken link, so a new revision epoch began. */
export function reconnectResetsCursor(previous: ConnectionInfo, next: ConnectionInfo): boolean {
  return next.phase === "live" && previous.phase !== "live" && previous.phase !== "connecting";
}

/** One-line status for the banner; never claims live when it is not. */
export function connectionMessage(info: ConnectionInfo, nowMs: number): string {
  switch (info.phase) {
    case "live":
      return "core link live";
    case "connecting":
      return "connecting to core…";
    case "degraded":
      return "snapshot delayed — core reply is late";
    case "invalid":
      return `core reply rejected: ${info.lastError ?? "contract violation"} — retrying`;
    case "down": {
      const seconds = Math.max(0, Math.ceil(((info.retryAtMs ?? nowMs) - nowMs) / 100) / 10);
      return `core disconnected — retrying in ${seconds.toFixed(1)} s${info.lastError ? ` (${info.lastError})` : ""}`;
    }
  }
}

/** Short label for the HUD chip. */
export function connectionLabel(info: ConnectionInfo): string {
  switch (info.phase) {
    case "live":
      return "LINK LIVE";
    case "connecting":
      return "CONNECTING";
    case "degraded":
      return "LINK DEGRADED";
    case "invalid":
      return "REPLY REJECTED";
    case "down":
      return "CORE OFFLINE";
  }
}
