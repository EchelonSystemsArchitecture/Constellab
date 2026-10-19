export const SCENE_CONFIG = {
  background: "#080B14",
  units: {
    // Scene unit = Earth radius. The core speaks kilometres (ECI), so the
    // renderer needs exactly one conversion; see scene/orbit.ts eciToScene().
    kmPerSceneUnit: 6371,
  },
  earth: {
    radius: 1,
    widthSegments: 128,
    heightSegments: 64,
    roughness: 0.42,
    metalness: 0.1,
  },
  texture: {
    width: 1024,
    height: 512,
    ocean: "#080B14",
    land: "#2E405A",
    ice: "#364B69",
    grid: "rgba(255, 118, 95, 0.2)",
    gridSpacingDeg: 30,
  },
  camera: {
    fovDeg: 45,
    near: 0.01,
    far: 100,
    position: [3.0, 1.8, 3.0] as const,
    target: [0, 0, 0] as const,
    minDistance: 1.35,
    maxDistance: 12,
    zoomFactor: 1.25,
    dampingFactor: 0.08,
  },
  lighting: {
    ambientColor: "#101827",
    ambientIntensity: 1.4,
    sunColor: "#FFF5EA",
    sunIntensity: 3.2,
    sunPosition: [4, 2.5, 4.5] as const,
  },
  renderer: {
    maxPixelRatio: 2,
    exposure: 1.05,
  },
  timeWarp: {
    // Simulation time multiplier: 1 = real time, up to 1,000,000x.
    min: 1,
    max: 1_000_000,
    default: 300,
  },
} as const;

