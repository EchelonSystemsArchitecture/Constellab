/**
 * Day 1 acceptance checks:
 *   1. Python core smoke tests (package import, status, config validation)
 *   2. Frontend build check (TypeScript + Vite production build)
 */
const { spawnSync } = require("child_process");
const path = require("path");

const root = path.join(__dirname, "..");

function run(cmd, args, opts = {}) {
  const res = spawnSync(cmd, args, { cwd: root, encoding: "utf8", ...opts });
  if (res.error) {
    return { code: 1, out: "", err: String(res.error) };
  }
  return { code: res.status, out: res.stdout ?? "", err: res.stderr ?? "" };
}

let failed = false;

console.log("== Python core smoke tests ==");
const py = run("python", ["-m", "unittest", "discover", "-s", "tests", "-v"], {
  cwd: path.join(root, "core"),
});
process.stdout.write(py.out);
if (py.err) process.stderr.write(py.err);
if (py.code !== 0) failed = true;

console.log("\n== Frontend build check ==");
const fe = run(process.execPath, [path.join("node_modules", "vite", "bin", "vite.js"), "build"], { cwd: root });
process.stdout.write(fe.out);
if (fe.err) process.stderr.write(fe.err);
if (fe.code !== 0) failed = true;

if (failed) {
  console.error("\nTESTS FAILED");
  process.exit(1);
}
console.log("\nALL CHECKS PASSED");
