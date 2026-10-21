/**
 * Day 11: one large-fleet renderer for any satellite count.
 *
 * - Markers are a single `InstancedMesh` (one draw call) with a stable id ->
 *   instance index map, so a 1,000-satellite snapshot costs one matrix write per
 *   satellite, not 1,000 meshes, materials and React updates.
 * - Orbit paths are de-duplicated by orbital geometry. A Walker shell of 1,000
 *   satellites spread over 25 planes draws 25 paths, not 1,000, and the number
 *   of drawn paths and their tessellation are bounded by `SCENE_CONFIG.fleet`.
 * - Selection is a single reticle mesh plus a per-instance scale, never a rebuild
 *   of the fleet.
 *
 * This module is deliberately free of React and of WebGL-only calls, so the
 * batching path can be exercised headlessly in tests and in the benchmark.
 */
import {
  BufferGeometry,
  Color,
  DoubleSide,
  DynamicDrawUsage,
  Group,
  InstancedMesh,
  Line,
  LineBasicMaterial,
  Matrix4,
  Mesh,
  MeshBasicMaterial,
  Object3D,
  Quaternion,
  RingGeometry,
  SphereGeometry,
  Vector3,
} from "three";
import type { OrbitElements, SatelliteState, SimulationSnapshot } from "../contract";
import { SCENE_CONFIG } from "./config";
import {
  BRAND_COLORS,
  createOrbitGeometry,
  createOrbitPlaneGeometry,
  eciToScene,
  getSatelliteColor,
} from "./orbit";

export type MarkerDetail = "high" | "low";

export interface PathSegmentTier {
  readonly maxSatellites: number;
  readonly segments: number;
}

export interface FleetStats {
  satellites: number;
  markerInstances: number;
  uniqueOrbits: number;
  orbitPaths: number;
  pathSegments: number;
  markerDetail: MarkerDetail;
}

/** Tessellation of a drawn orbit path for a fleet of this size. */
export function pathSegmentsFor(
  satelliteCount: number,
  tiers: readonly PathSegmentTier[] = SCENE_CONFIG.fleet.pathSegments,
): number {
  for (const tier of tiers) {
    if (satelliteCount <= tier.maxSatellites) return tier.segments;
  }
  return tiers[tiers.length - 1].segments;
}

/**
 * Identity of an orbit *path*. True anomaly is excluded: two satellites with the
 * same conic traverse the same line, so one path can serve both.
 */
export function orbitSignature(orbit: OrbitElements): string {
  const q = (value: number) => value.toFixed(4);
  return [
    q(orbit.semi_major_axis_km),
    q(orbit.eccentricity),
    q(orbit.inclination_deg),
    q(orbit.raan_deg),
    q(orbit.argument_of_perigee_deg),
  ].join("|");
}

/**
 * Choose which unique orbits stay drawn, spread evenly through the list so the
 * retained paths cover the whole shell instead of clustering in the first planes.
 * A pinned key (the selected satellite's orbit) is always kept.
 */
export function selectPathKeys(keys: readonly string[], budget: number, pinned?: string | null): string[] {
  if (budget <= 0 || keys.length === 0) return [];
  if (keys.length <= budget) return [...keys];
  const stride = keys.length / budget;
  const chosen: string[] = [];
  for (let i = 0; i < budget; i++) chosen.push(keys[Math.floor(i * stride)]);
  if (pinned && keys.includes(pinned) && !chosen.includes(pinned)) {
    chosen[chosen.length - 1] = pinned;
  }
  return chosen;
}

interface PathEntry {
  line: Line;
  material: LineBasicMaterial;
  segments: number;
}

interface PlaneEntry {
  mesh: Mesh;
  geometry: BufferGeometry;
  material: MeshBasicMaterial;
  key: string;
}

export class FleetRenderer {
  private readonly group = new Group();
  private readonly markerMaterial = new MeshBasicMaterial({ color: 0xffffff });
  private readonly selection: Mesh<RingGeometry, MeshBasicMaterial>;
  private readonly scratchMatrix = new Matrix4();
  private readonly scratchScale = new Vector3(1, 1, 1);
  private readonly scratchColor = new Color();
  private readonly identity = new Quaternion();

  private markers: InstancedMesh | null = null;
  private markerGeometry: SphereGeometry | null = null;
  private capacity = 0;
  private detail: MarkerDetail = "high";
  private indexById = new Map<string, number>();
  private positions = new Map<string, Vector3>();
  private paths = new Map<string, PathEntry>();
  private plane: PlaneEntry | null = null;
  private planeVisible = true;
  private orbitsVisible = true;
  private selectedId: string | null = null;
  private snapshot: SimulationSnapshot | null = null;
  private satelliteCount = 0;
  private uniqueOrbits = 0;
  private segments = pathSegmentsFor(4);

  constructor(private readonly parent: Object3D) {
    const ring = new RingGeometry(0.032, 0.042, 4);
    const ringMaterial = new MeshBasicMaterial({
      color: BRAND_COLORS.starlight,
      transparent: true,
      opacity: 0.85,
      wireframe: true,
    });
    this.selection = new Mesh(ring, ringMaterial);
    this.selection.rotation.z = Math.PI / 4;
    this.selection.visible = false;
    this.group.add(this.selection);
    this.parent.add(this.group);
  }

  /** Replace the displayed fleet with a snapshot (or clear it with null). */
  setSnapshot(snapshot: SimulationSnapshot | null) {
    this.snapshot = snapshot;
    this.apply();
  }

  /** Highlight a satellite without touching simulation state. */
  setSelection(id: string | null) {
    if (this.selectedId === id) return;
    this.selectedId = id;
    this.apply();
  }

  setOrbitsVisible(visible: boolean) {
    this.orbitsVisible = visible;
    for (const entry of this.paths.values()) entry.line.visible = visible;
  }

  /** Day 12 diagnostic: translucent orbit-plane layer for the selection. */
  setOrbitPlaneVisible(visible: boolean) {
    this.planeVisible = visible;
    if (this.plane) this.plane.mesh.visible = visible;
  }

  /** Scene-space position of a satellite, or null when it is not rendered. */
  positionOf(id: string): Vector3 | null {
    return this.positions.get(id) ?? null;
  }

  has(id: string): boolean {
    return this.indexById.has(id);
  }

  /** Stable id -> instance index mapping (exposed for tests and diagnostics). */
  instanceIndex(id: string): number | null {
    return this.indexById.get(id) ?? null;
  }

  /** A copy of one instance matrix, for tests and scene diagnostics. */
  instanceMatrix(id: string): Matrix4 | null {
    const index = this.indexById.get(id);
    if (index === undefined || !this.markers) return null;
    const matrix = new Matrix4();
    this.markers.getMatrixAt(index, matrix);
    return matrix;
  }

  ids(): string[] {
    return [...this.indexById.keys()];
  }

  stats(): FleetStats {
    return {
      satellites: this.satelliteCount,
      markerInstances: this.markers?.count ?? 0,
      uniqueOrbits: this.uniqueOrbits,
      orbitPaths: this.paths.size,
      pathSegments: this.segments,
      markerDetail: this.detail,
    };
  }

  /** Every object owned by the renderer, for leak checks. */
  children(): number {
    return this.group.children.length;
  }

  dispose() {
    this.releaseMarkers();
    for (const key of [...this.paths.keys()]) this.removePath(key);
    this.releasePlane();
    this.selection.geometry.dispose();
    this.selection.material.dispose();
    this.group.clear();
    this.parent.remove(this.group);
    this.indexById.clear();
    this.positions.clear();
    this.snapshot = null;
  }

  private apply() {
    const satellites: SatelliteState[] = this.snapshot?.satellites ?? [];
    this.satelliteCount = satellites.length;
    this.ensureMarkers(satellites.length);
    const markers = this.markers!;
    this.reindex(satellites);

    for (let index = 0; index < satellites.length; index++) {
      const sat = satellites[index];
      const instance = this.indexById.get(sat.id);
      if (instance === undefined) continue;
      let position = this.positions.get(sat.id);
      if (!position) {
        position = new Vector3();
        this.positions.set(sat.id, position);
      }
      position.copy(eciToScene(sat.position_eci_km));
      const scale = sat.id === this.selectedId ? SCENE_CONFIG.fleet.selectionScale : 1;
      this.scratchMatrix.compose(position, this.identity, this.scratchScale.setScalar(scale));
      markers.setMatrixAt(instance, this.scratchMatrix);
      markers.setColorAt(instance, this.scratchColor.setHex(getSatelliteColor(index)));
    }
    // Instances beyond the fleet size stay allocated but unrendered.
    markers.count = satellites.length;
    markers.instanceMatrix.needsUpdate = true;
    if (markers.instanceColor) markers.instanceColor.needsUpdate = true;

    this.updatePaths(satellites);
    this.updateSelection();
  }

  /**
   * Assign instance slots: survive ids keep their previous index, new ids take
   * the next free slot. Removing a satellite can never shuffle the others.
   */
  private reindex(satellites: readonly SatelliteState[]) {
    const next = new Map<string, number>();
    const used = new Set<number>();
    for (const sat of satellites) {
      const previous = this.indexById.get(sat.id);
      if (previous !== undefined && previous < this.capacity && !used.has(previous)) {
        next.set(sat.id, previous);
        used.add(previous);
      }
    }
    let cursor = 0;
    for (const sat of satellites) {
      if (next.has(sat.id)) continue;
      while (used.has(cursor)) cursor++;
      next.set(sat.id, cursor);
      used.add(cursor);
    }
    for (const id of [...this.positions.keys()]) {
      if (!next.has(id)) this.positions.delete(id);
    }
    this.indexById = next;
  }

  private ensureMarkers(count: number) {
    const detail: MarkerDetail = count <= SCENE_CONFIG.fleet.detailMarkerLimit ? "high" : "low";
    if (this.markers && this.capacity >= count && this.detail === detail) return;
    this.releaseMarkers();
    const radius = detail === "high" ? SCENE_CONFIG.fleet.markerRadius : SCENE_CONFIG.fleet.denseMarkerRadius;
    this.markerGeometry = new SphereGeometry(radius, detail === "high" ? 16 : 8, detail === "high" ? 12 : 6);
    this.capacity = Math.max(1, count);
    this.detail = detail;
    const markers = new InstancedMesh(this.markerGeometry, this.markerMaterial, this.capacity);
    markers.instanceMatrix.setUsage(DynamicDrawUsage);
    // The fleet spans the whole globe; skip the per-frame bounding-sphere test.
    markers.frustumCulled = false;
    this.markers = markers;
    this.group.add(markers);
  }

  private releaseMarkers() {
    if (!this.markers) return;
    this.group.remove(this.markers);
    this.markers.dispose();
    this.markerGeometry?.dispose();
    this.markers = null;
    this.markerGeometry = null;
    this.capacity = 0;
  }

  private updatePaths(satellites: readonly SatelliteState[]) {
    this.segments = pathSegmentsFor(satellites.length);
    const keyOrder: string[] = [];
    const orbitByKey = new Map<string, OrbitElements>();
    const colorByKey = new Map<string, number>();
    const keyById = new Map<string, string>();
    satellites.forEach((sat, index) => {
      if (!sat.orbit) return;
      const key = orbitSignature(sat.orbit);
      keyById.set(sat.id, key);
      if (!orbitByKey.has(key)) {
        orbitByKey.set(key, sat.orbit);
        colorByKey.set(key, getSatelliteColor(index));
        keyOrder.push(key);
      }
    });
    this.uniqueOrbits = keyOrder.length;

    const selectedKey = this.selectedId ? keyById.get(this.selectedId) ?? null : null;
    const visible = selectPathKeys(keyOrder, SCENE_CONFIG.fleet.maxOrbitPaths, selectedKey);
    const keep = new Set(visible);
    for (const key of [...this.paths.keys()]) {
      const entry = this.paths.get(key)!;
      if (!keep.has(key) || entry.segments !== this.segments) this.removePath(key);
    }

    for (const key of visible) {
      let entry = this.paths.get(key);
      if (!entry) {
        const material = new LineBasicMaterial({
          color: colorByKey.get(key) ?? BRAND_COLORS.ionTeal,
          transparent: true,
          opacity: 0.72,
        });
        const line = new Line(createOrbitGeometry(orbitByKey.get(key)!, this.segments), material);
        line.frustumCulled = false;
        this.group.add(line);
        entry = { line, material, segments: this.segments };
        this.paths.set(key, entry);
      }
      entry.line.visible = this.orbitsVisible;
    }

    this.syncPlane(selectedKey, orbitByKey);
  }

  private syncPlane(key: string | null, orbitByKey: Map<string, OrbitElements>) {
    if (!key) {
      if (this.plane) this.plane.mesh.visible = false;
      return;
    }
    if (this.plane?.key !== key) {
      this.releasePlane();
      const orbit = orbitByKey.get(key);
      if (!orbit) return;
      const geometry = createOrbitPlaneGeometry(orbit);
      const material = new MeshBasicMaterial({
        color: BRAND_COLORS.paleAurora,
        transparent: true,
        opacity: 0.075,
        side: DoubleSide,
        depthWrite: false,
      });
      const mesh = new Mesh(geometry, material);
      mesh.frustumCulled = false;
      this.plane = { mesh, geometry, material, key };
      this.group.add(mesh);
    }
    this.plane.mesh.visible = this.planeVisible;
  }

  private releasePlane() {
    if (!this.plane) return;
    this.group.remove(this.plane.mesh);
    this.plane.geometry.dispose();
    this.plane.material.dispose();
    this.plane = null;
  }

  private removePath(key: string) {
    const entry = this.paths.get(key);
    if (!entry) return;
    this.group.remove(entry.line);
    entry.line.geometry.dispose();
    entry.material.dispose();
    this.paths.delete(key);
  }

  private updateSelection() {
    const position = this.selectedId ? this.positions.get(this.selectedId) : undefined;
    this.selection.visible = Boolean(position);
    if (position) this.selection.position.copy(position);
    this.selection.scale.setScalar(SCENE_CONFIG.fleet.selectionScale);
  }
}
