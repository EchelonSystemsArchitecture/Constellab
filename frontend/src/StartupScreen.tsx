import { useEffect, useRef, useState } from "react";
import { ACESFilmicToneMapping, PerspectiveCamera, Vector3, WebGLRenderer } from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { OFFLINE_ASSETS } from "./scene/assets";
import { resetCamera } from "./scene/camera";
import { SCENE_CONFIG } from "./scene/config";
import { createEarthWorld } from "./scene/EarthWorld";
import { BROWSER_RUNTIME, startViewport } from "./scene/lifecycle";

const SPLASH_MS = 1600;

/**
 * First-run experience, in order:
 *   1. a white splash with the app icon and the "constellab" wordmark
 *   2. the rotating Earth with an Enter button (the Enter key works too)
 *   3. the orbiting viewport (App takes over)
 *
 * The Earth renderer mounts once on mount, so it is already running when the
 * splash fades away instead of stalling on the first frame.
 */
export function StartupScreen({ onLaunch }: { onLaunch: () => void }) {
  const viewport = useRef<HTMLDivElement>(null);
  const [stage, setStage] = useState<"splash" | "enter">("splash");

  useEffect(() => {
    const timer = setTimeout(() => setStage("enter"), SPLASH_MS);
    return () => clearTimeout(timer);
  }, []);

  useEffect(() => {
    if (stage !== "enter") return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Enter") return;
      event.preventDefault();
      onLaunch();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [stage, onLaunch]);

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
      // 3D unavailable, continue without it
    }

    return () => {
      stopViewport?.();
    };
  }, []);

  return (
    <div className="loading-screen" data-testid="startup-screen" data-stage={stage}>
      {stage === "enter" && (
        <div className="loading-screen__content">
          <img className="loading-screen__brand-wordmark" src="constellab-wordmark.svg" alt="constellab" />
          <p className="loading-screen__tagline">software-only crash-test lab for autonomous satellite swarms</p>
          <button className="loading-screen__enter-btn" onClick={onLaunch} data-testid="launch-button" autoFocus>
            Enter
          </button>
          <p className="loading-screen__enter-hint">
            or press <kbd>Enter</kbd>
          </p>
        </div>
      )}
      <div className="loading-screen__viewport" ref={viewport} />
      <div className="loading-screen__vignette" />
      <div
        className={`loading-screen__splash${stage === "splash" ? "" : " loading-screen__splash--hidden"}`}
        data-testid="splash"
        aria-hidden={stage !== "splash"}
      >
        <img className="splash__icon" src="constellab-icon.png" alt="" />
        <img className="splash__wordmark" src="constellab-wordmark.svg" alt="constellab" />
      </div>
    </div>
  );
}
