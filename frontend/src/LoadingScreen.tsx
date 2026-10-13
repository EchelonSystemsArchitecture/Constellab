import { useEffect, useRef, useState } from "react";
import {
  ACESFilmicToneMapping,
  PerspectiveCamera,
  Vector3,
  WebGLRenderer,
} from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { OFFLINE_ASSETS } from "./scene/assets";
import { resetCamera } from "./scene/camera";
import { SCENE_CONFIG } from "./scene/config";
import { createEarthWorld } from "./scene/EarthWorld";
import { BROWSER_RUNTIME, startViewport } from "./scene/lifecycle";

export function LoadingScreen({ onReady }: { onReady: () => void }) {
  const viewport = useRef<HTMLDivElement>(null);
  const [status, setStatus] = useState("initializing core…");
  const onReadyRef = useRef(onReady);
  onReadyRef.current = onReady;

  useEffect(() => {
    if (!viewport.current) return;

    let renderer: WebGLRenderer;
    let controls: OrbitControls;
    let stopViewport: (() => void) | undefined;
    let world: ReturnType<typeof createEarthWorld> | undefined;

    try {
      const config = SCENE_CONFIG;
      renderer = new WebGLRenderer({ antialias: true, alpha: true });
      renderer.toneMapping = ACESFilmicToneMapping;
      renderer.toneMappingExposure = config.renderer.exposure;
      renderer.domElement.setAttribute("aria-label", "Rotating Earth");

      const camera = new PerspectiveCamera(config.camera.fovDeg, 1, config.camera.near, config.camera.far);
      resetCamera(camera, new Vector3());

      controls = new OrbitControls(camera, renderer.domElement);
      controls.enableDamping = true;
      controls.dampingFactor = config.camera.dampingFactor;
      controls.enablePan = false;
      controls.minDistance = config.camera.minDistance;
      controls.maxDistance = config.camera.maxDistance;
      controls.autoRotate = true;
      controls.autoRotateSpeed = 0.5;

      world = createEarthWorld(OFFLINE_ASSETS);
      viewport.current.appendChild(renderer.domElement);

      stopViewport = startViewport(viewport.current, {
        resize: (width, height, pixelRatio) => {
          camera.aspect = width / height;
          camera.updateProjectionMatrix();
          renderer.setPixelRatio(pixelRatio);
          renderer.setSize(width, height);
        },
        render: () => {
          controls.update();
          renderer.render(world!.scene, camera);
        },
        dispose: () => {
          controls.dispose();
          world?.dispose();
          renderer.dispose();
          renderer.forceContextLoss();
          renderer.domElement.remove();
        },
      }, BROWSER_RUNTIME, config.renderer.maxPixelRatio);
    } catch {
      setStatus("3D unavailable — loading without preview");
    }

    const statusTimer = setTimeout(() => {
      setStatus("connecting to core…");
    }, 1500);

    const readyTimer = setTimeout(() => {
      onReadyRef.current();
    }, 3500);

    return () => {
      clearTimeout(statusTimer);
      clearTimeout(readyTimer);
      stopViewport?.();
    };
  }, []);

  return (
    <div className="loading-screen">
      <div className="loading-screen__content">
        <div className="loading-screen__brand">
          <span className="loading-screen__logo">◆</span>
          <h1 className="loading-screen__title">constellab</h1>
        </div>
        <p className="loading-screen__tagline">software-only crash-test lab for autonomous satellite swarms</p>
        <div className="loading-screen__status">
          <span className="loading-screen__spinner" />
          <span className="loading-screen__status-text">{status}</span>
        </div>
      </div>
      <div className="loading-screen__viewport" ref={viewport} />
      <div className="loading-screen__vignette" />
    </div>
  );
}
