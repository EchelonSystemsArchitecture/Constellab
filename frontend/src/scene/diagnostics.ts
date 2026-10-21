/**
 * Day 12: visual diagnostics.
 *
 * Everything here is a pure derivation from a snapshot plus the local arrival
 * time. Toggles only change what is *displayed*; they can never alter the
 * simulation, the clock or a satellite position.
 */
import type { SatelliteState, SimulationSnapshot } from "../contract";
import { SCENE_CONFIG } from "./config";
import type { SatelliteProjection } from "./EarthScene";
import { simulationUtc } from "./selection";

export interface DiagnosticToggles {
  /** Satellite id labels near their markers. */
  ids: boolean;
  /** Translucent fill of the selected satellite's orbital plane. */
  orbitPlane: boolean;
  /** Simulated UTC + elapsed simulation time. */
  simTime: boolean;
  /** Selected satellite id/ECI position/altitude. */
  selectedPosition: boolean;
  /** Age of the last accepted snapshot, with a staleness verdict. */
  snapshotAge: boolean;
}

export const DEFAULT_DIAGNOSTIC_TOGGLES: DiagnosticToggles = {
  ids: false,
  orbitPlane: false,
  simTime: true,
  selectedPosition: true,
  snapshotAge: true,
};

export type DiagnosticTone = "ok" | "warn" | "bad" | "muted";

export interface DiagnosticRow {
  key: string;
  label: string;
  value: string;
  available: boolean;
  tone: DiagnosticTone;
}

export interface DiagnosticModel {
  rows: DiagnosticRow[];
  ageMs: number | null;
  stale: boolean;
}

const UNAVAILABLE = "UNAVAILABLE";

/** Milliseconds since the snapshot arrived, or null when there is none. */
export function snapshotAgeMs(receivedAtMs: number | null, nowMs: number): number | null {
  if (receivedAtMs === null || !Number.isFinite(receivedAtMs) || !Number.isFinite(nowMs)) return null;
  return Math.max(0, nowMs - receivedAtMs);
}

/** Human-readable age: `420 ms`, `3.1 s`, `2 m 05 s`. */
export function formatAge(ageMs: number | null): string {
  if (ageMs === null) return UNAVAILABLE;
  if (ageMs < 1000) return `${Math.round(ageMs)} ms`;
  if (ageMs < 60_000) return `${(ageMs / 1000).toFixed(1)} s`;
  const minutes = Math.floor(ageMs / 60_000);
  const seconds = Math.round((ageMs % 60_000) / 1000);
  return `${minutes} m ${String(seconds).padStart(2, "0")} s`;
}

export function stalenessTone(ageMs: number | null): DiagnosticTone {
  if (ageMs === null) return "muted";
  if (ageMs >= SCENE_CONFIG.diagnostics.staleBadMs) return "bad";
  if (ageMs >= SCENE_CONFIG.diagnostics.staleWarnMs) return "warn";
  return "ok";
}

function formatVector(position: readonly number[] | undefined, digits: number): string {
  if (!position || position.length !== 3 || !position.every((value) => Number.isFinite(value))) {
    return UNAVAILABLE;
  }
  return position.map((value) => value.toFixed(digits)).join(", ");
}

/**
 * Rows for the diagnostics panel. A toggle that is off contributes no row, so
 * the panel is itself the authoritative list of what is currently displayed.
 */
export function diagnosticsModel(input: {
  snapshot: SimulationSnapshot | null;
  toggles: DiagnosticToggles;
  receivedAtMs: number | null;
  nowMs: number;
  renderFps?: number | null;
  fleetSatellites?: number | null;
  selectedId?: string | null;
}): DiagnosticModel {
  const { snapshot, toggles, receivedAtMs, nowMs } = input;
  const clock = snapshot?.clock ?? null;
  const ageMs = snapshotAgeMs(receivedAtMs, nowMs);
  const tone = stalenessTone(ageMs);
  const rows: DiagnosticRow[] = [];

  if (toggles.simTime) {
    const utc = simulationUtc(clock);
    rows.push({
      key: "sim_utc",
      label: "SIM UTC",
      value: utc,
      available: utc !== UNAVAILABLE,
      tone: "muted",
    });
    rows.push({
      key: "sim_time",
      label: "SIM ELAPSED",
      value: clock && Number.isFinite(clock.simulation_time_s)
        ? `${clock.simulation_time_s.toFixed(1)} s  ·  ×${clock.time_scale}  ·  ${clock.paused ? "PAUSED" : "RUNNING"}`
        : UNAVAILABLE,
      available: Boolean(clock),
      tone: "muted",
    });
  }

  if (toggles.snapshotAge) {
    rows.push({
      key: "snapshot_age",
      label: "SNAPSHOT AGE",
      value: ageMs === null ? UNAVAILABLE : formatAge(ageMs),
      available: ageMs !== null,
      tone,
    });
    const fleet = input.fleetSatellites ?? snapshot?.satellites.length ?? null;
    rows.push({
      key: "fleet",
      label: "FLEET",
      value: fleet === null ? UNAVAILABLE : `${fleet} satellites`,
      available: fleet !== null,
      tone: "muted",
    });
    if (typeof input.renderFps === "number" && Number.isFinite(input.renderFps)) {
      rows.push({
        key: "render_fps",
        label: "RENDER",
        value: `${input.renderFps.toFixed(0)} fps`,
        available: true,
        tone: "muted",
      });
    }
  }

  if (toggles.selectedPosition) {
    const selectedId = input.selectedId ?? null;
    const satellite: SatelliteState | undefined = selectedId
      ? snapshot?.satellites.find((sat) => sat.id === selectedId)
      : undefined;
    // Without a snapshot there is no entity list to resolve the id against, so
    // the id alone is not evidence that the selection exists.
    const resolvedId = snapshot ? selectedId : null;
    rows.push({
      key: "selection",
      label: "SELECTION",
      value: resolvedId ?? (snapshot ? "NONE" : UNAVAILABLE),
      available: Boolean(resolvedId),
      tone: resolvedId ? "ok" : "muted",
    });
    rows.push({
      key: "selected_position",
      label: "SELECTED ECI",
      value: formatVector(satellite?.position_eci_km, 1),
      available: Boolean(satellite),
      tone: "muted",
    });
    const radius = satellite
      ? Math.hypot(...satellite.position_eci_km)
      : Number.NaN;
    rows.push({
      key: "selected_altitude",
      label: "SELECTED ALT",
      value: Number.isFinite(radius) ? `${(radius - 6378.137).toFixed(1)} km` : UNAVAILABLE,
      available: Number.isFinite(radius),
      tone: "muted",
    });
  }

  return {
    rows,
    ageMs,
    stale: ageMs !== null && ageMs >= SCENE_CONFIG.diagnostics.staleWarnMs,
  };
}

/**
 * Which projections get an id label. Labels are bounded and never overlap the
 * whole screen: dense fleets show the selection plus an evenly spread sample.
 */
export function visibleLabelIds(
  projections: readonly SatelliteProjection[],
  toggles: DiagnosticToggles,
  selectedId: string | null,
  budget: number = SCENE_CONFIG.fleet.maxLabels,
): string[] {
  if (!toggles.ids) return [];
  const visible = projections.filter((projection) => !projection.isOccluded);
  if (visible.length === 0) return [];
  const ids: string[] = [];
  if (selectedId && visible.some((projection) => projection.id === selectedId)) ids.push(selectedId);
  if (visible.length <= budget) {
    for (const projection of visible) {
      if (projection.id !== selectedId) ids.push(projection.id);
    }
    return ids;
  }
  const remaining = Math.max(0, budget - ids.length);
  if (remaining === 0) return ids;
  const stride = visible.length / remaining;
  for (let i = 0; i < remaining; i++) {
    const projection = visible[Math.min(visible.length - 1, Math.floor(i * stride))];
    if (!ids.includes(projection.id)) ids.push(projection.id);
  }
  return ids;
}
