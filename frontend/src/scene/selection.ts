/**
 * Day 7: satellite selection, camera focus and typed inspector data.
 *
 * Everything here is a pure function of a snapshot. Selecting a satellite never
 * writes to the simulation state; it only derives view data, so a selection can
 * not change a simulation trace.
 */
import type { PerspectiveCamera, Vector3 } from "three";
import type { SatelliteProjection } from "./EarthScene";
import type { SatelliteState, SimulationClock, SimulationSnapshot } from "../contract";
import { SCENE_CONFIG } from "./config";

/** WGS-84 equatorial radius; altitude is measured above this surface. */
export const EARTH_RADIUS_KM = 6378.137;

export interface InspectorRow {
  key: string;
  label: string;
  /** Human-readable value, or UNAVAILABLE when the snapshot does not carry it. */
  value: string;
  unit?: string;
  available: boolean;
}

export interface InspectorSection {
  id: string;
  title: string;
  rows: InspectorRow[];
}

export type SelectionState =
  | { kind: "none" }
  | { kind: "missing"; id: string }
  | { kind: "selected"; satellite: SatelliteState };

const UNAVAILABLE = "UNAVAILABLE";

function formatNumber(value: number | undefined | null, digits: number): string {
  return typeof value === "number" && Number.isFinite(value) ? value.toFixed(digits) : UNAVAILABLE;
}

function row(key: string, label: string, value: string, unit?: string): InspectorRow {
  const available = value !== UNAVAILABLE;
  return unit === undefined ? { key, label, value, available } : { key, label, value, unit, available };
}

function numericRow(key: string, label: string, value: number | undefined | null, digits: number, unit: string): InspectorRow {
  return row(key, label, formatNumber(value, digits), unit);
}

/** UTC instant of the snapshot clock, or UNAVAILABLE when it can not be formed. */
export function simulationUtc(clock: SimulationClock | null | undefined): string {
  if (!clock || typeof clock.epoch_utc !== "string" || !Number.isFinite(clock.simulation_time_s)) {
    return UNAVAILABLE;
  }
  const epochMs = Date.parse(clock.epoch_utc);
  if (!Number.isFinite(epochMs)) return UNAVAILABLE;
  return new Date(epochMs + clock.simulation_time_s * 1000).toISOString().replace(/\.\d{3}Z$/, "Z");
}

/** Radius of a scene-space point in kilometres, using the scene's own scale. */
export function radiusKm(position: readonly [number, number, number]): number {
  return Math.hypot(position[0], position[1], position[2]);
}

/**
 * Resolve a selected id against the current snapshot.
 *
 * A selection that the new snapshot no longer carries is reported as `missing`
 * instead of silently keeping the previous satellite's numbers on screen.
 */
export function resolveSelection(id: string | null, satellites: SatelliteState[]): SelectionState {
  if (!id) return { kind: "none" };
  const satellite = satellites.find((s) => s.id === id);
  return satellite ? { kind: "selected", satellite } : { kind: "missing", id };
}

/**
 * Build the inspector from snapshot schema fields only.
 *
 * Orbit elements are optional in the contract, so a satellite without them gets
 * explicit UNAVAILABLE rows rather than invented zeros.
 */
export function satelliteInspectorSections(
  satellite: SatelliteState | null,
  clock: SimulationClock | null | undefined,
  snapshot: SimulationSnapshot | null = null,
): InspectorSection[] {
  if (!satellite) return [];

  const [x, y, z] = satellite.position_eci_km;
  const [vx, vy, vz] = satellite.velocity_eci_km_s;
  const radius = satellite.position_eci_km.every((n) => Number.isFinite(n)) ? radiusKm(satellite.position_eci_km) : undefined;
  const speed = [vx, vy, vz].every((n) => Number.isFinite(n)) ? Math.hypot(vx, vy, vz) : undefined;
  const orbit = satellite.orbit;

  return [
    {
      id: "identity",
      title: "IDENTITY",
      rows: [
        row("id", "ENTITY ID", satellite.id),
        row("scenario_id", "SCENARIO", snapshot?.scenario_id ?? UNAVAILABLE),
        row("producer", "PRODUCER", snapshot ? `${snapshot.producer.name} v${snapshot.producer.version}` : UNAVAILABLE),
        row("schema_version", "CONTRACT", snapshot?.schema_version ?? UNAVAILABLE),
      ],
    },
    {
      id: "clock",
      title: "TIME BASE",
      rows: [
        row("epoch_utc", "EPOCH (UTC)", clock?.epoch_utc ?? UNAVAILABLE),
        row("simulation_time_s", "SIM TIME", formatNumber(clock?.simulation_time_s, 1), "s"),
        row("sim_utc", "SIM UTC", simulationUtc(clock)),
        row("time_scale", "TIME SCALE", formatNumber(clock?.time_scale, 0), "×"),
        row("clock_state", "CLOCK STATE", clock ? (clock.paused ? "PAUSED" : "RUNNING") : UNAVAILABLE),
      ],
    },
    {
      id: "orbit",
      title: "ORBIT ELEMENTS",
      rows: [
        numericRow("semi_major_axis_km", "SEMI-MAJOR AXIS", orbit?.semi_major_axis_km, 3, "km"),
        numericRow("eccentricity", "ECCENTRICITY", orbit?.eccentricity, 5, ""),
        numericRow("inclination_deg", "INCLINATION", orbit?.inclination_deg, 3, "°"),
        numericRow("raan_deg", "RAAN", orbit?.raan_deg, 3, "°"),
        numericRow("argument_of_perigee_deg", "ARG OF PERIGEE", orbit?.argument_of_perigee_deg, 3, "°"),
        numericRow("true_anomaly_deg", "TRUE ANOMALY", orbit?.true_anomaly_deg, 3, "°"),
      ],
    },
    {
      id: "position",
      title: "POSITION — ECI",
      rows: [
        numericRow("position_x", "X", x, 3, "km"),
        numericRow("position_y", "Y", y, 3, "km"),
        numericRow("position_z", "Z", z, 3, "km"),
        numericRow("radius", "RADIUS", radius, 3, "km"),
        numericRow("altitude", "ALTITUDE", radius === undefined ? undefined : radius - EARTH_RADIUS_KM, 1, "km"),
      ],
    },
    {
      id: "velocity",
      title: "VELOCITY — ECI",
      rows: [
        numericRow("velocity_x", "VX", vx, 5, "km/s"),
        numericRow("velocity_y", "VY", vy, 5, "km/s"),
        numericRow("velocity_z", "VZ", vz, 5, "km/s"),
        numericRow("speed", "SPEED", speed, 5, "km/s"),
      ],
    },
  ];
}

/**
 * Nearest visible satellite marker to a screen point, or null when the click
 * misses every marker. Occluded satellites (behind Earth) are not pickable.
 */
export function pickSatellite(
  projections: readonly SatelliteProjection[],
  screenX: number,
  screenY: number,
  maxPixels = 18,
): string | null {
  let bestId: string | null = null;
  let bestDistance = maxPixels;
  for (const projection of projections) {
    if (projection.isOccluded) continue;
    const distance = Math.hypot(projection.screenX - screenX, projection.screenY - screenY);
    if (distance <= bestDistance) {
      bestDistance = distance;
      bestId = projection.id;
    }
  }
  return bestId;
}

export interface FocusTarget {
  target: Vector3;
}

/**
 * Centre the camera on `position` without changing the zoom level: the camera
 * keeps its current viewing direction and distance, and only its aim moves.
 * Returns the distance used so callers can report/undo it.
 */
export function focusCamera(
  camera: PerspectiveCamera,
  controls: FocusTarget,
  position: Vector3,
  distance?: number,
): number {
  const direction = camera.position.clone().sub(controls.target);
  const currentDistance = direction.length();
  if (currentDistance < 1e-6) direction.set(1, 0.6, 1);
  direction.normalize();

  const wanted = distance ?? (currentDistance > 1e-6 ? currentDistance : SCENE_CONFIG.camera.minDistance * 2);
  const clamped = Math.min(
    SCENE_CONFIG.camera.maxDistance,
    Math.max(SCENE_CONFIG.camera.minDistance, wanted),
  );

  controls.target.copy(position);
  camera.position.copy(position).addScaledVector(direction, clamped);
  camera.lookAt(position);
  camera.updateMatrixWorld();
  return clamped;
}
