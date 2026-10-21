/**
 * Day 11/13: repeatable large-fleet benchmark (opt-in, never part of `npm test`).
 *
 * It measures the *real* renderer batching path — `FleetRenderer.setSnapshot`
 * from compiled `src/scene/fleet.ts` — against snapshots produced by the real
 * core, for 100 / 500 / 1,000-satellite scenarios. Metrics are distributions
 * (p50 / p95 / max), not the fastest single frame, and every report carries
 * machine + runtime metadata so numbers are comparable only on like hardware.
 *
 * What it does NOT measure: GPU draw time and compositing. That needs a browser
 * and is verified separately in the app (the canvas exposes `data-frame-p50-ms`
 * / `data-frame-p95-ms` from the live render loop).
 */
import { spawnSync } from "node:child_process";
import { mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { performance } from "node:perf_hooks";
import { Scene } from "three";
import type { OrbitElements, SimulationClock, SimulationSnapshot } from "../contract";
import { FleetRenderer } from "../scene/fleet";

const ROOT = path.resolve(__dirname, "..", "..", "..");
const CORE = path.join(ROOT, "core");
const SCENARIOS = ["swarm-100", "swarm-500", "swarm-1000"];
const RECORDS = 120;

interface Record {
  t: number;
  scenario_id: string;
  clock: SimulationClock;
  satellites: { id: string; position_eci_km: [number, number, number]; velocity_eci_km_s: [number, number, number] }[];
}

function pythonCommand(): string {
  for (const candidate of ["python", "python3"]) {
    const probe = spawnSync(candidate, ["-c", "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)"], { encoding: "utf8" });
    if (!probe.error && probe.status === 0) return candidate;
  }
  throw new Error("Python >= 3.10 not found on PATH (tried python, python3)");
}

function core(args: string[]): string {
  const sep = process.platform === "win32" ? ";" : ":";
  const env = { ...process.env, PYTHONPATH: CORE + (process.env.PYTHONPATH ? sep + process.env.PYTHONPATH : "") };
  const result = spawnSync(pythonCommand(), args, { cwd: CORE, env, encoding: "utf8", maxBuffer: 256 * 1024 * 1024 });
  if (result.error || result.status !== 0) {
    throw new Error(`constellab_core ${args.join(" ")} failed: ${result.error ?? result.stderr}`);
  }
  return result.stdout;
}

function percentile(sorted: number[], fraction: number): number {
  return sorted[Math.min(sorted.length - 1, Math.floor(fraction * sorted.length))];
}

function loadRecords(scenario: string): { records: Record[]; orbits: Map<string, OrbitElements> } {
  const effective = JSON.parse(core(["-m", "constellab_core", "validate", scenario])).effective_config as {
    satellites: { id: string; orbit: OrbitElements }[];
  };
  const out = path.join(os.tmpdir(), `constellab-bench-${scenario}-${process.pid}.ndjson`);
  try {
    const summary = core([
      "-m", "constellab_core", "run", scenario,
      "--duration", "120", "--step", "1", "--out", out,
    ]);
    const records = readFileSync(out, "utf8")
      .split("\n")
      .filter((line) => line.length > 0)
      .slice(0, RECORDS)
      .map((line) => JSON.parse(line) as Record);
    if (records.length !== RECORDS) {
      throw new Error(`${scenario}: expected ${RECORDS} records, got ${records.length} (${summary})`);
    }
    return { records, orbits: new Map(effective.satellites.map((sat) => [sat.id, sat.orbit])) };
  } finally {
    rmSync(out, { force: true });
  }
}

function toSnapshot(record: Record, orbits: Map<string, OrbitElements>): SimulationSnapshot {
  return {
    schema_version: "1.1.0",
    scenario_id: record.scenario_id,
    producer: { name: "constellab-core", version: "bench" },
    clock: record.clock,
    satellites: record.satellites.map((sat) => ({ ...sat, orbit: orbits.get(sat.id) })),
  };
}

const results = [];
for (const scenario of SCENARIOS) {
  const { records, orbits } = loadRecords(scenario);
  const snapshots = records.map((record) => toSnapshot(record, orbits));
  const scene = new Scene();
  const fleet = new FleetRenderer(scene);
  // Warm up the allocator and the instance buffers before timing.
  for (let i = 0; i < 5; i++) fleet.setSnapshot(snapshots[i % snapshots.length]);

  const heapBefore = process.memoryUsage().heapUsed;
  const samples: number[] = [];
  for (const snapshot of snapshots) {
    const started = performance.now();
    fleet.setSnapshot(snapshot);
    samples.push(performance.now() - started);
  }
  const heapAfter = process.memoryUsage().heapUsed;
  const sorted = [...samples].sort((a, b) => a - b);
  const stats = fleet.stats();
  results.push({
    scenario,
    satellites: stats.satellites,
    snapshots: samples.length,
    mean_ms: Number((samples.reduce((sum, value) => sum + value, 0) / samples.length).toFixed(3)),
    p50_ms: Number(percentile(sorted, 0.5).toFixed(3)),
    p95_ms: Number(percentile(sorted, 0.95).toFixed(3)),
    max_ms: Number(percentile(sorted, 1).toFixed(3)),
    markers: stats.markerInstances,
    unique_orbits: stats.uniqueOrbits,
    orbit_paths: stats.orbitPaths,
    path_segments: stats.pathSegments,
    marker_detail: stats.markerDetail,
    scene_objects: fleet.children(),
    heap_delta_mb: Number(((heapAfter - heapBefore) / 1048576).toFixed(2)),
  });
  fleet.dispose();
}

const report = {
  generated_at: new Date().toISOString(),
  method: "FleetRenderer.setSnapshot over 120 real core snapshots (scene batching; excludes GPU draw)",
  environment: {
    node: process.version,
    platform: process.platform,
    arch: process.arch,
    cpu: os.cpus()[0]?.model ?? "unknown",
    cores: os.cpus().length,
    total_memory_gb: Number((os.totalmem() / 1073741824).toFixed(1)),
    machine: `${os.platform()} ${os.release()}`,
  },
  results,
};

const outPath = path.join(ROOT, "benchmarks", "fleet-benchmark.json");
mkdirSync(path.dirname(outPath), { recursive: true });
writeFileSync(outPath, JSON.stringify(report, null, 2) + "\n", "utf8");

console.log(`fleet benchmark · ${report.environment.node} · ${report.environment.cpu} (${report.environment.cores} cores)`);
for (const result of results) {
  console.log(
    `${result.scenario.padEnd(11)} ${String(result.satellites).padStart(5)} sats · ` +
    `p50 ${String(result.p50_ms).padStart(6)} ms · p95 ${String(result.p95_ms).padStart(6)} ms · ` +
    `max ${String(result.max_ms).padStart(6)} ms · ${String(result.orbit_paths).padStart(3)} paths · ` +
    `${result.scene_objects} scene objects`,
  );
}
console.log(`wrote ${path.relative(ROOT, outPath)}`);
