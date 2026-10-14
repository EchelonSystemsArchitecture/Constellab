import { BufferGeometry, Float32BufferAttribute, Line, LineBasicMaterial, Mesh, MeshBasicMaterial, SphereGeometry, Vector3 } from "three";
import type { OrbitElements, SatelliteState, SatelliteConfig } from "../contract";

export interface SatelliteVisuals {
  orbitLine: Line;
  satelliteMesh: Mesh;
}

const EARTH_RADIUS_KM = 6371;
const VISUAL_SCALE = 1 / EARTH_RADIUS_KM;

export function createOrbitGeometry(orbit: OrbitElements): BufferGeometry {
  const { semi_major_axis_km, eccentricity, inclination_deg, raan_deg, argument_of_perigee_deg, true_anomaly_deg } = orbit;

  const segments = 128;
  const positions = new Float32Array((segments + 1) * 3);

  const a = semi_major_axis_km * VISUAL_SCALE;
  const e = eccentricity;

  const inc = inclination_deg * Math.PI / 180;
  const raan = raan_deg * Math.PI / 180;
  const argPe = argument_of_perigee_deg * Math.PI / 180;
  const trueAnomaly = true_anomaly_deg * Math.PI / 180;

  const cosInc = Math.cos(inc);
  const sinInc = Math.sin(inc);
  const cosRaan = Math.cos(raan);
  const sinRaan = Math.sin(raan);
  const cosArgPe = Math.cos(argPe);
  const sinArgPe = Math.sin(argPe);

  for (let i = 0; i <= segments; i++) {
    const theta = (i / segments) * Math.PI * 2;
    const E = eccentricAnomalyFromTrueAnomaly(theta, e);
    const r = a * (1 - e * Math.cos(E));

    const cosTheta = Math.cos(theta);
    const sinTheta = Math.sin(theta);

    const xOrbit = r * cosTheta;
    const yOrbit = r * sinTheta * cosInc;
    const zOrbit = r * sinTheta * sinInc;

    const cosArgPeTheta = Math.cos(theta + argPe);
    const sinArgPeTheta = Math.sin(theta + argPe);

    const x = xOrbit * cosRaan - yOrbit * sinRaan;
    const y = xOrbit * sinRaan + yOrbit * cosRaan;
    const z = zOrbit;

    positions[i * 3] = x;
    positions[i * 3 + 1] = z;
    positions[i * 3 + 2] = -y;
  }

  const geometry = new BufferGeometry();
  geometry.setAttribute('position', new Float32BufferAttribute(positions, 3));
  return geometry;
}

function eccentricAnomalyFromTrueAnomaly(trueAnomaly: number, e: number): number {
  const cosF = Math.cos(trueAnomaly);
  const sinF = Math.sin(trueAnomaly);
  const E = Math.atan2(sinF * Math.sqrt(1 - e * e), cosF + e);
  return E;
}

export function satellitePositionFromOrbit(orbit: OrbitElements, trueAnomalyDeg: number): Vector3 {
  const { semi_major_axis_km, eccentricity, inclination_deg, raan_deg, argument_of_perigee_deg } = orbit;

  const a = semi_major_axis_km * VISUAL_SCALE;
  const e = eccentricity;

  const inc = inclination_deg * Math.PI / 180;
  const raan = raan_deg * Math.PI / 180;
  const argPe = argument_of_perigee_deg * Math.PI / 180;
  const trueAnomaly = trueAnomalyDeg * Math.PI / 180;

  const cosInc = Math.cos(inc);
  const sinInc = Math.sin(inc);
  const cosRaan = Math.cos(raan);
  const sinRaan = Math.sin(raan);
  const cosArgPe = Math.cos(argPe);
  const sinArgPe = Math.sin(argPe);

  const E = eccentricAnomalyFromTrueAnomaly(trueAnomaly, e);
  const r = a * (1 - e * Math.cos(E));

  const cosTheta = Math.cos(trueAnomaly);
  const sinTheta = Math.sin(trueAnomaly);

  const xOrbit = r * cosTheta;
  const yOrbit = r * sinTheta * cosInc;
  const zOrbit = r * sinTheta * sinInc;

  const x = xOrbit * cosRaan - yOrbit * sinRaan;
  const y = xOrbit * sinRaan + yOrbit * cosRaan;
  const z = zOrbit;

  return new Vector3(x, z, -y);
}

export function createSatelliteVisuals(sat: SatelliteState | SatelliteConfig, color: number): SatelliteVisuals {
  const orbit = sat.orbit!;

  const orbitGeometry = createOrbitGeometry(orbit);
  const orbitMaterial = new LineBasicMaterial({
    color,
    transparent: true,
    opacity: 0.6,
    linewidth: 1,
  });
  const orbitLine = new Line(orbitGeometry, orbitMaterial);

  const satGeometry = new SphereGeometry(0.02, 12, 12);
  const satMaterial = new MeshBasicMaterial({ color });
  const satelliteMesh = new Mesh(satGeometry, satMaterial);

  if ('position_eci_km' in sat) {
    const pos = sat.position_eci_km;
    satelliteMesh.position.set(pos[0] * VISUAL_SCALE, pos[1] * VISUAL_SCALE, pos[2] * VISUAL_SCALE);
  } else {
    const trueAnomaly = orbit.true_anomaly_deg;
    const pos = satellitePositionFromOrbit(orbit, trueAnomaly);
    satelliteMesh.position.copy(pos);
  }

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