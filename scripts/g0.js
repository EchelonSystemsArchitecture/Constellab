/**
 * G0 visual-gate runner (Day 14).
 *
 *   npm run g0
 *
 * Runs the checks that can be automated from a clean checkout and prints the
 * checklist with the evidence for each item. The WebGL draw itself is verified
 * in the app (a headless Node process has no GPU); the canvas exposes frame
 * p50/p95 and fleet counters for that manual/scripted check.
 */
const { spawnSync } = require("child_process");
const os = require("os");
const path = require("path");

const root = path.join(__dirname, "..");
const tsc = path.join(root, "node_modules", "typescript", "bin", "tsc");
const results = [];

function step(name, command, args, extra = {}) {
  process.stdout.write(`\n== ${name} ==\n`);
  const started = Date.now();
  const result = spawnSync(command, args, { cwd: root, stdio: "inherit", ...extra });
  const ok = !result.error && result.status === 0;
  results.push({ name, ok, ms: Date.now() - started, error: result.error });
  return ok;
}

const compiled = step("compile test suites", process.execPath, [tsc, "-p", "frontend/tsconfig.test.json"]);
if (compiled) {
  step("end-to-end vertical slice (real core, 4 and 1,000 satellites)", process.execPath,
    ["--test", "frontend/.test-out/e2e/__tests__/*.test.js"]);
  step("scene + fleet instancing tests", process.execPath,
    ["--test", "frontend/.test-out/scene/__tests__/*.test.js"]);
}
step("compile fleet benchmark", process.execPath,
  [tsc, "-p", "frontend/tsconfig.bench.json"]);
step("fleet benchmark run (distributions + machine metadata)", process.execPath,
  ["frontend/.bench-out/bench/fleet-bench.js"]);
step("frontend production build", process.execPath, ["node_modules/vite/bin/vite.js", "build"]);

const failed = results.filter((result) => !result.ok);
console.log("\n================ G0 VISUAL GATE ================");
console.log(`environment : ${process.platform} ${os.release()} · ${os.arch()} · node ${process.version}`);
console.log(`cpu         : ${os.cpus()[0]?.model ?? "unknown"} (${os.cpus().length} cores)`);
console.log(`memory      : ${(os.totalmem() / 1073741824).toFixed(1)} GB`);
for (const result of results) {
  console.log(`${result.ok ? "PASS" : "FAIL"}  ${result.name} (${(result.ms / 1000).toFixed(1)}s)`);
}
console.log("-----------------------------------------------");
console.log("Manual/visual evidence still required for:");
console.log("  - Earth, satellites, orbit paths and camera controls rendering in the browser");
console.log("  - selection highlight, inspector and config loading in one session");
console.log("  - canvas data-frame-p50-ms / data-frame-p95-ms at 4 and 1,000 satellites");
console.log("  Start it with: npm run demo  →  http://localhost:5173?phase=app");
console.log("===============================================");

if (failed.length > 0) {
  console.error(`\nG0 AUTOMATED CHECKS FAILED: ${failed.map((result) => result.name).join(", ")}`);
  process.exit(1);
}
console.log("\nG0 AUTOMATED CHECKS PASSED");
