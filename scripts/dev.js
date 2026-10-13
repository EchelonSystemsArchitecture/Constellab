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

let electronLaunched = false;
function tryLaunchElectron() {
  if (electronLaunched) return;
  const viteProc = procs[1];
  viteProc.stdout.on("data", (d) => {
    const text = d.toString();
    if (text.includes("Local:") && !electronLaunched) {
      electronLaunched = true;
      console.log("[dev] Vite ready, launching Electron...");
      const electron = spawn("npx", ["electron", "."], {
        cwd: root,
        stdio: ["ignore", "pipe", "pipe"],
        shell: true,
      });
      electron.stdout.on("data", (d) => process.stdout.write(d));
      electron.stderr.on("data", (d) => process.stderr.write(d));
      electron.on("exit", (code) => {
        if (code !== null && code !== 0) {
          console.error(`[dev] electron exited with code ${code}`);
          shutdown();
        }
      });
      procs.push(electron);
    }
  });
}

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

// Try launching Electron after Vite prints "Local:"
tryLaunchElectron();

// Also set a fallback timeout
setTimeout(tryLaunchElectron, 3000);

function shutdown() {
  for (const p of procs) {
    if (!p.killed) p.kill();
  }
  process.exit(0);
}

process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);