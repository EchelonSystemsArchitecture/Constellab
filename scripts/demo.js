/**
 * One-command demo (Day 14): local core + Vite, no Electron packaging step.
 *
 *   npm run demo
 *
 * Then open http://localhost:5173?phase=app (the startup splash is skipped by
 * `?phase=app`). Electron is intentionally not launched here: the goal is a
 * browser-visible G0 slice that works from a clean checkout.
 */
const { spawn } = require("child_process");
const path = require("path");
const { pythonCommand, pythonEnv } = require("./py");

const root = path.join(__dirname, "..");
const coreDir = path.join(root, "core");
const CORE_PORT = 8765;
const WEB_PORT = 5173;
const procs = [];

function launch(name, command, args, options) {
  const child = spawn(command, args, { ...options, stdio: ["ignore", "pipe", "pipe"] });
  const prefix = `[${name}]`;
  child.stdout.on("data", (data) => process.stdout.write(`${prefix} ${data}`));
  child.stderr.on("data", (data) => process.stderr.write(`${prefix} ${data}`));
  child.on("exit", (code) => {
    if (code !== null && code !== 0 && !stopping) {
      console.error(`${prefix} exited with code ${code}; shutting down`);
      shutdown(code);
    }
  });
  procs.push(child);
  return child;
}

const core = launch(
  "core",
  pythonCommand(),
  ["-m", "constellab_core", "serve", "--port", String(CORE_PORT)],
  { cwd: coreDir, env: pythonEnv() },
);

launch("web", "npx", ["vite", "--port", String(WEB_PORT), "--strictPort"], {
  cwd: root,
  shell: true,
});

let stopping = false;
function shutdown(code = 0) {
  if (stopping) return;
  stopping = true;
  for (const proc of procs) {
    if (!proc.killed) proc.kill();
  }
  setTimeout(() => process.exit(code), 150);
}

process.on("SIGINT", () => shutdown(0));
process.on("SIGTERM", () => shutdown(0));

setTimeout(() => {
  if (stopping) return;
  console.log("");
  console.log(`ConstellaLab demo`);
  console.log(`  core  http://127.0.0.1:${CORE_PORT}/api/status  (pid ${core.pid})`);
  console.log(`  view  http://localhost:${WEB_PORT}?phase=app`);
  console.log("  stop  Ctrl+C");
  console.log("");
}, 1500);
