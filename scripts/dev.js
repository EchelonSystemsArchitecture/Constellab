/**
 * Single-command development launcher.
 *
 * Starts the Python core service and the Vite dev server as child processes,
 * pipes their output to the terminal and shuts both down on Ctrl+C.
 */
const { spawn } = require("child_process");
const path = require("path");
const { pythonCommand, pythonEnv } = require("./py");

const root = path.join(__dirname, "..");
const coreDir = path.join(root, "core");

const procs = [
  spawn(pythonCommand(), ["-m", "constellab_core", "serve", "--port", "8765"], {
    cwd: coreDir,
    env: pythonEnv(),
    stdio: ["ignore", "pipe", "pipe"],
    shell: false,
  }),
  spawn("npx", ["vite"], {
    cwd: root,
    stdio: ["ignore", "pipe", "pipe"],
    shell: true,
  }),
];

for (const p of procs) {
  p.stdout.on("data", (d) => process.stdout.write(d));
  p.stderr.on("data", (d) => process.stderr.write(d));
  p.on("exit", (code) => {
    if (code !== null && code !== 0) {
      console.error(`[dev] a child process exited with code ${code}; shutting down`);
      shutdown();
    }
  });
}

function shutdown() {
  for (const p of procs) {
    if (!p.killed) p.kill();
  }
  process.exit(0);
}

process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);
