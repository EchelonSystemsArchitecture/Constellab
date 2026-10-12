/**
 * Acceptance checks (run by `npm test`):
 *   1. Python core tests (contract round-trips, fixtures, HTTP bridge, CLI)
 *   2. Generated TypeScript contract is in sync with the JSON Schema
 *   3. Frontend type-check
 *   4. TypeScript contract tests against the shared fixtures
 *   5. Frontend production build
 */
const { spawnSync } = require("child_process");
const path = require("path");
const { pythonCommand, pythonEnv } = require("./py");

const root = path.join(__dirname, "..");
const python = pythonCommand();
const tsc = path.join(root, "node_modules", "typescript", "bin", "tsc");
const vite = path.join(root, "node_modules", "vite", "bin", "vite.js");

const steps = [
  ["Python core tests", python, ["-m", "unittest", "discover", "-s", "tests", "-v"], { cwd: path.join(root, "core") }],
  ["Generated contract up to date", python, [path.join("scripts", "gen_contract.py"), "--check"]],
  ["Frontend type-check", process.execPath, [tsc, "-p", "frontend", "--noEmit"]],
  ["Compile contract tests", process.execPath, [tsc, "-p", path.join("frontend", "tsconfig.test.json")]],
  ["TypeScript contract tests", process.execPath, ["--test", path.join("frontend", ".test-out", "contract", "__tests__", "contract.test.js")]],
  ["Frontend build", process.execPath, [vite, "build"]],
];

let failed = false;
for (const [name, cmd, args, opts] of steps) {
  console.log(`\n== ${name} ==`);
  const res = spawnSync(cmd, args, { cwd: root, stdio: "inherit", env: pythonEnv(), ...opts });
  if (res.error || res.status !== 0) {
    console.error(`[test] ${name} failed${res.error ? `: ${res.error}` : ""}`);
    failed = true;
    break;
  }
}

if (failed) {
  console.error("\nTESTS FAILED");
  process.exit(1);
}
console.log("\nALL CHECKS PASSED");
