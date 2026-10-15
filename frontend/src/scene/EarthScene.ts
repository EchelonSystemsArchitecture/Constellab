import {
  ACESFilmicToneMapping, PerspectiveCamera, Vector3, WebGLRenderer, Scene, Line, Mesh,
} from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import type { SimulationSnapshot } from "../contract";
import type { SceneAssets } from "./assets";
import { REAL_EARTH_ASSETS } from "./assets";
import { resetCamera, zoomCamera } from "./camera";
import { SCENE_CONFIG } from "./config";
import { createEarthWorld } from "./EarthWorld";
import { BROWSER_RUNTIME, startViewport } from "./lifecycle";
import { createSatelliteVisuals, eciToScene, getSatelliteColor } from "./orbit";

export class EarthScene {
  private readonly renderer: WebGLRenderer;
  private readonly camera: PerspectiveCamera;
  private readonly controls: OrbitControls;
  private readonly stopViewport: () => void;
  private readonly worldScene: Scene;
  private readonly satelliteLines: Line[] = [];
  private readonly satelliteMeshes: Map<string, { mesh: Mesh; index: number }> = new Map();
  private disposed = false;

  constructor(host: HTMLElement, assets: SceneAssets = REAL_EARTH_ASSETS) {
    const config = SCENE_CONFIG;
    this.renderer = new WebGLRenderer({ antialias: true });
    this.renderer.toneMapping = ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = config.renderer.exposure;
    this.renderer.domElement.setAttribute("aria-label", "3D Earth with satellite orbits. Drag to orbit, scroll to zoom.");
    this.renderer.domElement.setAttribute("role", "img");
    this.camera = new PerspectiveCamera(config.camera.fovDeg, 1, config.camera.near, config.camera.far);
    resetCamera(this.camera, new Vector3());
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = config.camera.dampingFactor;
    this.controls.enablePan = false;
    this.controls.minDistance = config.camera.minDistance;
    this.controls.maxDistance = config.camera.maxDistance;
    this.reset();

    let world;
    try {
      world = createEarthWorld(assets);
    } catch (error) {
      this.controls.dispose();
      this.renderer.dispose();
      throw error;
    }
    this.worldScene = world.scene;
    host.appendChild(this.renderer.domElement);
    this.stopViewport = startViewport(host, {
      resize: (width, height, pixelRatio) => {
        this.camera.aspect = width / height;
        this.camera.updateProjectionMatrix();
        this.renderer.setPixelRatio(pixelRatio);
        this.renderer.setSize(width, height);
      },
      render: () => {
        this.controls.update();
        this.renderer.render(this.worldScene, this.camera);
      },
      dispose: () => {
        this.controls.dispose();
        world.dispose();
        this.renderer.dispose();
        this.renderer.forceContextLoss();
        this.renderer.domElement.remove();
      },
    }, BROWSER_RUNTIME, config.renderer.maxPixelRatio);
  }

  setSnapshot(snapshot: SimulationSnapshot | null) {
    if (this.disposed) return;
    const canvas = this.renderer.domElement;
    if (snapshot) {
      canvas.dataset.scenarioId = snapshot.scenario_id;
      canvas.dataset.simulationTimeS = String(snapshot.clock.simulation_time_s);
      this.updateSatellites(snapshot);
    } else {
      delete canvas.dataset.scenarioId;
      delete canvas.dataset.simulationTimeS;
      this.clearSatellites();
    }
  }

  private updateSatellites(snapshot: SimulationSnapshot) {
    const currentIds = new Set(snapshot.satellites.map(s => s.id));

    for (const [id, { mesh }] of this.satelliteMeshes) {
      if (!currentIds.has(id)) {
        this.worldScene.remove(mesh);
        const lineIdx = this.satelliteLines.findIndex(l => (l.userData as any).meshId === id);
        if (lineIdx >= 0) {
          const line = this.satelliteLines[lineIdx];
          line.geometry.dispose();
          (line.material as any).dispose?.();
          this.satelliteLines.splice(lineIdx, 1);
        }
        this.satelliteMeshes.delete(id);
      }
    }

    snapshot.satellites.forEach((sat, i) => {
      const color = getSatelliteColor(i);
      const existing = this.satelliteMeshes.get(sat.id);

      if (existing) {
        existing.mesh.position.copy(eciToScene(sat.position_eci_km));
      } else {
        const visuals = createSatelliteVisuals(sat, color);
        (visuals.orbitLine.userData as any).meshId = sat.id;
        this.worldScene.add(visuals.orbitLine);
        this.worldScene.add(visuals.satelliteMesh);
        this.satelliteLines.push(visuals.orbitLine);
        this.satelliteMeshes.set(sat.id, { mesh: visuals.satelliteMesh, index: i });
      }
    });
  }

  private clearSatellites() {
    for (const line of this.satelliteLines) {
      this.worldScene.remove(line);
      line.geometry.dispose();
      (line.material as any).dispose?.();
    }
    this.satelliteLines.length = 0;
    for (const { mesh } of this.satelliteMeshes.values()) {
      this.worldScene.remove(mesh);
      mesh.geometry.dispose();
      (mesh.material as any).dispose?.();
    }
    this.satelliteMeshes.clear();
  }

  zoom(direction: "in" | "out") {
    if (this.disposed) return;
    zoomCamera(this.camera, this.controls.target,
      direction === "in" ? 1 / SCENE_CONFIG.camera.zoomFactor : SCENE_CONFIG.camera.zoomFactor);
    this.controls.update();
  }

  reset() {
    if (this.disposed) return;
    const damping = this.controls.enableDamping;
    this.controls.enableDamping = false;
    this.controls.reset();
    resetCamera(this.camera, this.controls.target);
    this.controls.saveState();
    this.controls.update();
    this.controls.enableDamping = damping;
  }

  dispose() {
    if (this.disposed) return;
    this.disposed = true;
    this.clearSatellites();
    this.stopViewport();
  }
}
