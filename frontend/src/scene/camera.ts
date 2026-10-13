import { PerspectiveCamera, Vector3 } from "three";
import { SCENE_CONFIG } from "./config";

export function resetCamera(camera: PerspectiveCamera, target: Vector3) {
  camera.up.set(0, 0, 1);
  camera.position.set(...SCENE_CONFIG.camera.position);
  target.set(...SCENE_CONFIG.camera.target);
  camera.lookAt(target);
  camera.updateProjectionMatrix();
}

export function zoomCamera(camera: PerspectiveCamera, target: Vector3, factor: number) {
  const offset = camera.position.clone().sub(target);
  const distance = Math.min(
    SCENE_CONFIG.camera.maxDistance,
    Math.max(SCENE_CONFIG.camera.minDistance, offset.length() * factor),
  );
  camera.position.copy(target).add(offset.setLength(distance));
  camera.updateMatrixWorld();
}
