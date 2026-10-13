import {
  ACESFilmicToneMapping, PerspectiveCamera, Vector3, WebGLRenderer,
} from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import type { SimulationSnapshot } from "../contract";
import { OFFLINE_ASSETS, SceneAssets } from "./assets";
import { resetCamera, zoomCamera } from "./camera";
import { SCENE_CONFIG } from "./config";
import { createEarthWorld } from "./EarthWorld";
import { BROWSER_RUNTIME, startViewport } from "./lifecycle";

export class EarthScene {
  private readonly renderer: WebGLRenderer;
  private readonly camera: PerspectiveCamera;
  private readonly controls: OrbitControls;
  private readonly stopViewport: () => void;
  private disposed = false;

  constructor(host: HTMLElement, assets: SceneAssets = OFFLINE_ASSETS) {
    const config = SCENE_CONFIG;
    this.renderer = new WebGLRenderer({ antialias: true });
    this.renderer.toneMapping = ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = config.renderer.exposure;
    this.renderer.domElement.setAttribute("aria-label", "3D Earth placeholder. Drag to orbit, scroll to zoom.");
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
    host.appendChild(this.renderer.domElement);
    this.stopViewport = startViewport(host, {
      resize: (width, height, pixelRatio) => {
        this.camera.aspect = width / height;
        this.camera.updateProjectionMatrix();
        this.renderer.setPixelRatio(pixelRatio);
        this.renderer.setSize(width, height);
      },
      render: () => {
        // Damping is camera-only; render frames never advance simulation time.
        this.controls.update();
        this.renderer.render(world.scene, this.camera);
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
    // Metadata only on Day 3; entity geometry is a separate Day 4 consumer.
    const canvas = this.renderer.domElement;
    if (snapshot) {
      canvas.dataset.scenarioId = snapshot.scenario_id;
      canvas.dataset.simulationTimeS = String(snapshot.clock.simulation_time_s);
    } else {
      delete canvas.dataset.scenarioId;
      delete canvas.dataset.simulationTimeS;
    }
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
    this.stopViewport();
  }
}
