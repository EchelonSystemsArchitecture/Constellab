import {
  BufferGeometry,
  Float32BufferAttribute,
  Line,
  LineBasicMaterial,
  Mesh,
  MeshBasicMaterial,
  SphereGeometry,
  Vector3,
} from "three";
import type { OrbitElements, SatelliteState, SatelliteConfig, Vector3Km } from "../contract";
import { SCENE_CONFIG } from "./config";

export interface SatelliteVisuals {
  orbitLine: Line;
  satelliteMesh: Mesh;
}

const KM_PER_SCENE_UNIT = SCENE_CONFIG.units.kmPerSceneUnit;
const SEGMENTS = 180;

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

export function createOrbitGeometry(orbit: OrbitElements): BufferGeometry {
  const positions = new Float32Array((SEGMENTS + 1) * 3);
  for (let i = 0; i <= SEGMENTS; i++) {
    const nu = (i / SEGMENTS) * Math.PI * 2;
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

export function createSatelliteVisuals(sat: SatelliteState | SatelliteConfig, color: number): SatelliteVisuals {
  const orbit = sat.orbit!;

  const orbitLine = new Line(
    createOrbitGeometry(orbit),
    new LineBasicMaterial({ color, transparent: true, opacity: 0.6 }),
  );

  const satelliteMesh = new Mesh(
    new SphereGeometry(0.02, 12, 12),
    new MeshBasicMaterial({ color }),
  );

  satelliteMesh.position.copy(
    "position_eci_km" in sat
      ? eciToScene(sat.position_eci_km)
      : satellitePositionFromOrbit(orbit, orbit.true_anomaly_deg),
  );

  return { orbitLine, satelliteMesh };
}

export function getSatelliteColor(index: number): number {
  const colors = [
    0x00d4aa,
    0xff6b6b,
    0x4da3ff,
    0xffd93d,
    0xff9f43,
    0xa55eea,
    0x26de81,
    0xea8685,
  ];
  return colors[index % colors.length];
}
