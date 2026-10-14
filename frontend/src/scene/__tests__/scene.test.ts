import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { test } from "node:test";
import { PerspectiveCamera, SRGBColorSpace, Texture, Vector3 } from "three";
import type { SatelliteConfig } from "../../contract";
import { generateEarthTexture } from "../assets";
import { resetCamera, zoomCamera } from "../camera";
import { SCENE_CONFIG } from "../config";
import { createEarthWorld } from "../EarthWorld";
import { startViewport, ViewportRuntime } from "../lifecycle";
import { createOrbitGeometry, eciToScene, satellitePositionFromOrbit } from "../orbit";

const ROOT = path.resolve(__dirname, "..", "..", "..", "..");
const DEMO = JSON.parse(
  readFileSync(path.join(ROOT, "core", "constellab_core", "data", "scenario_four_satellites.json"), "utf8"),
) as { satellites: SatelliteConfig[] };

test("ECI -> scene mapping keeps the contract frame (Z is north)", () => {
  const point = eciToScene([SCENE_CONFIG.units.kmPerSceneUnit, 0, 0]);
  assert.ok(Math.abs(point.x - 1) < 1e-12);
  assert.ok(Math.abs(point.y) < 1e-12);
  const north = eciToScene([0, 0, SCENE_CONFIG.units.kmPerSceneUnit]);
  assert.ok(Math.abs(north.z - 1) < 1e-12, "north must stay on the scene +Z axis");
});

test("orbit paths share one conic and one mapping with satellite positions", () => {
  for (const sat of DEMO.satellites) {
    const orbit = sat.orbit;
    const geometry = createOrbitGeometry(orbit);
    const attribute = geometry.getAttribute("position");
    const segments = attribute.count - 1;
    // Every sampled path point is exactly where the position function places it.
    for (const index of [0, 1, segments / 2, segments]) {
      const expected = satellitePositionFromOrbit(orbit, (index / segments) * 360);
      // The path buffer is Float32, so agreement is to float precision.
      assert.ok(Math.abs(attribute.getX(index) - expected.x) < 1e-6, `${sat.id} sample ${index} x`);
      assert.ok(Math.abs(attribute.getY(index) - expected.y) < 1e-6, `${sat.id} sample ${index} y`);
      assert.ok(Math.abs(attribute.getZ(index) - expected.z) < 1e-6, `${sat.id} sample ${index} z`);
    }
    // The path is closed and bounded by the element ellipse.
    const scale = SCENE_CONFIG.units.kmPerSceneUnit;
    const radii: number[] = [];
    for (let i = 0; i < attribute.count; i++) {
      radii.push(Math.hypot(attribute.getX(i), attribute.getY(i), attribute.getZ(i)));
    }
    const a = orbit.semi_major_axis_km / scale;
    assert.ok(Math.abs(Math.min(...radii) - a * (1 - orbit.eccentricity)) < 0.01, `${sat.id} perigee`);
    assert.ok(Math.abs(Math.max(...radii) - a * (1 + orbit.eccentricity)) < 0.01, `${sat.id} apogee`);
    // The epoch marker sits on its own trajectory line.
    const epoch = satellitePositionFromOrbit(orbit, orbit.true_anomaly_deg);
    const nearest = Math.min(
      ...Array.from({ length: geometry.getAttribute("position").count }, (_, i) =>
        Math.hypot(attribute.getX(i) - epoch.x, attribute.getY(i) - epoch.y, attribute.getZ(i) - epoch.z),
      ),
    );
    assert.ok(nearest < 0.03, `${sat.id} epoch marker is ${nearest} scene units off its path`);
  }
});

function harness() {
  let nextId = 0;
  const frames = new Map<number, () => void>();
  let resizeCallback = () => {};
  const host = { clientWidth: 800, clientHeight: 600 };
  const sizes: number[][] = [];
  let draws = 0;
  let disposed = 0;
  let disconnected = 0;
  const runtime: ViewportRuntime = {
    requestFrame: (callback) => {
      frames.set(++nextId, callback);
      return nextId;
    },
    cancelFrame: (id) => { frames.delete(id); },
    observeResize: (_, callback) => {
      resizeCallback = callback;
      return () => { disconnected++; };
    },
    pixelRatio: () => 3,
  };
  const callbacks = {
    resize: (...size: number[]) => { sizes.push(size); },
    render: () => { draws++; },
    dispose: () => { disposed++; },
  };
  return {
    host, runtime, callbacks, frames, sizes,
    resize: () => resizeCallback(),
    get draws() { return draws; },
    get disposed() { return disposed; },
    get disconnected() { return disconnected; },
    tick() {
      const [id, callback] = [...frames.entries()][0];
      frames.delete(id);
      callback();
    },
  };
}

test("resize updates one viewport, caps pixel ratio and never starts another render loop", () => {
  const h = harness();
  const stop = startViewport(h.host, h.callbacks, h.runtime, 2);
  assert.deepEqual(h.sizes[0], [800, 600, 2]);
  for (let i = 0; i < 100; i++) {
    h.host.clientWidth = 400 + i;
    h.resize();
    h.tick();
    assert.equal(h.frames.size, 1);
  }
  assert.equal(h.draws, 100);
  assert.deepEqual(h.sizes.at(-1), [499, 600, 2]);
  h.host.clientWidth = 0;
  h.host.clientHeight = 0;
  h.resize();
  assert.deepEqual(h.sizes.at(-1), [1, 1, 2]);
  stop();
});

test("unmount is idempotent, disconnects resize and cancels even a late frame", () => {
  const h = harness();
  const stop = startViewport(h.host, h.callbacks, h.runtime, 2);
  const lateFrame = [...h.frames.values()][0];
  stop();
  stop();
  lateFrame();
  h.resize();
  assert.equal(h.frames.size, 0);
  assert.equal(h.disconnected, 1);
  assert.equal(h.disposed, 1);
  assert.equal(h.draws, 0);
  assert.equal(h.sizes.length, 1);
});

test("StrictMode mount-cleanup-remount leaves only the current loop", () => {
  const h = harness();
  const first = startViewport(h.host, h.callbacks, h.runtime, 2);
  first();
  const second = startViewport(h.host, h.callbacks, h.runtime, 2);
  assert.equal(h.frames.size, 1);
  h.tick();
  assert.equal(h.draws, 1);
  second();
  assert.equal(h.frames.size, 0);
  assert.equal(h.disposed, 2);
});

test("camera zoom preserves target/direction, clamps limits and resets exactly", () => {
  const camera = new PerspectiveCamera();
  const target = new Vector3();
  resetCamera(camera, target);
  const direction = camera.position.clone().sub(target).normalize();
  const distance = camera.position.distanceTo(target);
  zoomCamera(camera, target, 1 / SCENE_CONFIG.camera.zoomFactor);
  assert.ok(Math.abs(camera.position.distanceTo(target) - distance / 1.25) < 1e-10);
  assert.ok(camera.position.clone().sub(target).normalize().distanceTo(direction) < 1e-10);
  for (let i = 0; i < 100; i++) zoomCamera(camera, target, 0.8);
  assert.ok(Math.abs(camera.position.distanceTo(target) - SCENE_CONFIG.camera.minDistance) < 1e-10);
  for (let i = 0; i < 100; i++) zoomCamera(camera, target, 1.25);
  assert.ok(Math.abs(camera.position.distanceTo(target) - SCENE_CONFIG.camera.maxDistance) < 1e-10);
  resetCamera(camera, target);
  assert.deepEqual(camera.position.toArray(), [...SCENE_CONFIG.camera.position]);
  assert.deepEqual(target.toArray(), [0, 0, 0]);
  assert.deepEqual(camera.up.toArray(), [0, 0, 1]);
});

test("Earth uses replaceable local assets and releases geometry, material and texture once", () => {
  const texture = new Texture();
  let created = 0;
  const world = createEarthWorld({ createEarthTexture: () => { created++; return texture; } });
  assert.equal(created, 1);
  assert.equal(world.earth.material.map, texture);
  assert.equal(world.earth.geometry.parameters.radius, SCENE_CONFIG.earth.radius);
  assert.equal(world.scene.children.length, 3);
  const counts = { geometry: 0, material: 0, texture: 0 };
  world.earth.geometry.addEventListener("dispose", () => { counts.geometry++; });
  world.earth.material.addEventListener("dispose", () => { counts.material++; });
  texture.addEventListener("dispose", () => { counts.texture++; });
  world.dispose();
  world.dispose();
  assert.deepEqual(counts, { geometry: 1, material: 1, texture: 1 });
  assert.equal(world.scene.children.length, 0);
});

test("schematic Earth texture is generated on canvas, with no image loader or network", () => {
  const calls: string[] = [];
  const ctx = {
    fillRect: () => { calls.push("fillRect"); },
    beginPath: () => { calls.push("beginPath"); },
    moveTo: () => {},
    lineTo: () => {},
    closePath: () => {},
    fill: () => { calls.push("fill"); },
    stroke: () => { calls.push("stroke"); },
  };
  const canvas = { width: 0, height: 0, getContext: () => ctx } as unknown as HTMLCanvasElement;
  const texture = generateEarthTexture(canvas);
  assert.equal(texture.image, canvas);
  assert.equal(texture.colorSpace, SRGBColorSpace);
  assert.equal(canvas.width, SCENE_CONFIG.texture.width);
  assert.equal(canvas.height, SCENE_CONFIG.texture.height);
  assert.equal(calls.filter((call) => call === "fill").length, 7);
  assert.ok(calls.includes("stroke"));
  texture.dispose();
  assert.throws(
    () => generateEarthTexture({ getContext: () => null } as unknown as HTMLCanvasElement),
    /2D canvas/,
  );
});
