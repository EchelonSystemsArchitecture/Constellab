import {
  BufferGeometry,
  Float32BufferAttribute,
  Vector3,
} from "three";
import type { OrbitElements, Vector3Km } from "../contract";
import { SCENE_CONFIG } from "./config";

const KM_PER_SCENE_UNIT = SCENE_CONFIG.units.kmPerSceneUnit;
/** Default tessellation of a drawn orbit path (4-satellite / small fleets). */
export const SEGMENTS = 180;

/**
 * Map an Earth-centred inertial position (km, +Z = north) to scene units.
 *
 * The viewport keeps the contract's frame: the scene is Z-up, which is why the
 * camera's up vector is +Z and the Earth texture's pole is rotated onto +Z in
 * `EarthWorld`. Orbit paths and satellite positions must use this one mapping,
 * otherwise a position derived from a snapshot lands off its own path.
 */
export function eciToScene(position: Vector3Km): Vector3 {
  return new Vector3(position[0], position[1], position[2]).multiplyScalar(1 / KM_PER_SCENE_UNIT);
}

/** Rotate a perifocal-plane point into ECI: R3(raan) . R1(inc) . R3(argPerigee). */
function perifocalToEci(x: number, y: number, orbit: OrbitElements): Vector3Km {
  const inc = (orbit.inclination_deg * Math.PI) / 180;
  const raan = (orbit.raan_deg * Math.PI) / 180;
  const argPerigee = (orbit.argument_of_perigee_deg * Math.PI) / 180;

  const x1 = x * Math.cos(argPerigee) - y * Math.sin(argPerigee);
  const y1 = x * Math.sin(argPerigee) + y * Math.cos(argPerigee);
  const y2 = y1 * Math.cos(inc);
  const z2 = y1 * Math.sin(inc);
  return [x1 * Math.cos(raan) - y2 * Math.sin(raan), x1 * Math.sin(raan) + y2 * Math.cos(raan), z2];
}

/** Conic radius at true anomaly: r = p / (1 + e cos nu), p = a (1 - e^2). */
function radiusAtTrueAnomaly(orbit: OrbitElements, trueAnomalyRad: number): number {
  const p = orbit.semi_major_axis_km * (1 - orbit.eccentricity ** 2);
  return p / (1 + orbit.eccentricity * Math.cos(trueAnomalyRad));
}

/**
 * Position on an orbit at a given true anomaly, in scene units.
 *
 * This describes the same ellipse the core propagates along; it is geometry for
 * the drawn path, not a second source of orbital state (the snapshot owns that).
 */
export function satellitePositionFromOrbit(orbit: OrbitElements, trueAnomalyDeg: number): Vector3 {
  const nu = (trueAnomalyDeg * Math.PI) / 180;
  const r = radiusAtTrueAnomaly(orbit, nu);
  const [x, y, z] = perifocalToEci(r * Math.cos(nu), r * Math.sin(nu), orbit);
  return eciToScene([x, y, z]);
}

export function createOrbitGeometry(orbit: OrbitElements, segments: number = SEGMENTS): BufferGeometry {
  const count = Math.max(8, Math.floor(segments));
  const positions = new Float32Array((count + 1) * 3);
  for (let i = 0; i <= count; i++) {
    const nu = (i / count) * Math.PI * 2;
    const r = radiusAtTrueAnomaly(orbit, nu);
    const [x, y, z] = perifocalToEci(r * Math.cos(nu), r * Math.sin(nu), orbit);
    const point = eciToScene([x, y, z]);
    positions[i * 3] = point.x;
    positions[i * 3 + 1] = point.y;
    positions[i * 3 + 2] = point.z;
  }
  const geometry = new BufferGeometry();
  geometry.setAttribute("position", new Float32BufferAttribute(positions, 3));
  return geometry;
}

/**
 * Translucent triangle fan filling an orbit's plane, for the "orbit plane"
 * diagnostic overlay. The vertices are the same conic points as the path, so the
 * plane can never disagree with the drawn trajectory.
 */
export function createOrbitPlaneGeometry(orbit: OrbitElements, segments = 96): BufferGeometry {
  const count = Math.max(8, Math.floor(segments));
  const vertices: number[] = [];
  for (let i = 0; i < count; i++) {
    const nu = (i / count) * Math.PI * 2;
    const r = radiusAtTrueAnomaly(orbit, nu);
    const [x, y, z] = perifocalToEci(r * Math.cos(nu), r * Math.sin(nu), orbit);
    const point = eciToScene([x, y, z]);
    vertices.push(point.x, point.y, point.z);
  }
  // Triangle fan around the orbit centroid (the focus for a two-body ellipse).
  const center = new Vector3();
  for (let i = 0; i < count; i++) {
    center.x += vertices[i * 3];
    center.y += vertices[i * 3 + 1];
    center.z += vertices[i * 3 + 2];
  }
  center.divideScalar(count);
  const positions: number[] = [];
  for (let i = 0; i < count; i++) {
    const next = (i + 1) % count;
    positions.push(center.x, center.y, center.z);
    positions.push(vertices[i * 3], vertices[i * 3 + 1], vertices[i * 3 + 2]);
    positions.push(vertices[next * 3], vertices[next * 3 + 1], vertices[next * 3 + 2]);
  }
  const geometry = new BufferGeometry();
  geometry.setAttribute("position", new Float32BufferAttribute(positions, 3));
  return geometry;
}

export const BRAND_COLORS = {
  void: 0x080b14,
  observatory: 0x101827,
  orbitNavy: 0x1b2b4a,
  coreBlue: 0x3d68b2,
  ionTeal: 0x6f9b97,       // Nominal
  paleAurora: 0xb7d8c8,
  starlight: 0xe7e9ed,
  spectralLilac: 0xc8bde5, // Divergent
  solarGold: 0xf0c777,     // Caution
  anomalyCoral: 0xff765f,  // Anomaly
  telemetryGrey: 0x7d8598,
  deepInk: 0x202531,
} as const;

export function getSatelliteColor(index: number): number {
  const colors = [
    BRAND_COLORS.ionTeal,      // Sat 0: Nominal (Teal)
    BRAND_COLORS.anomalyCoral,  // Sat 1: Anomaly (Coral - matches True Anomaly in ref)
    BRAND_COLORS.coreBlue,      // Sat 2: Active tracking (Core blue)
    BRAND_COLORS.solarGold,     // Sat 3: Caution (Solar gold)
    BRAND_COLORS.spectralLilac, // Sat 4: Divergent behavior (Lilac)
    BRAND_COLORS.paleAurora,    // Sat 5: Pale aurora
    BRAND_COLORS.starlight,     // Sat 6: Starlight
  ];
  return colors[index % colors.length];
}
