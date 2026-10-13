import {
  AmbientLight, Color, DirectionalLight, Mesh, MeshStandardMaterial, Scene, SphereGeometry,
} from "three";
import type { SceneAssets } from "./assets";
import { SCENE_CONFIG } from "./config";

export function createEarthWorld(assets: SceneAssets) {
  const config = SCENE_CONFIG;
  const scene = new Scene();
  scene.background = new Color(config.background);
  const texture = assets.createEarthTexture();
  const geometry = new SphereGeometry(config.earth.radius, config.earth.widthSegments, config.earth.heightSegments);
  const material = new MeshStandardMaterial({
    map: texture,
    roughness: config.earth.roughness,
    metalness: config.earth.metalness,
  });
  const earth = new Mesh(geometry, material);
  // Three.js sphere geometry is Y-up; reserve world Z for the contract's north/ECI axis.
  earth.rotation.x = Math.PI / 2;
  scene.add(earth);
  scene.add(new AmbientLight(config.lighting.ambientColor, config.lighting.ambientIntensity));
  const sun = new DirectionalLight(config.lighting.sunColor, config.lighting.sunIntensity);
  sun.position.set(...config.lighting.sunPosition);
  scene.add(sun);
  let disposed = false;
  return {
    scene,
    earth,
    dispose() {
      if (disposed) return;
      disposed = true;
      geometry.dispose();
      material.dispose();
      texture.dispose();
      scene.clear();
    },
  };
}
