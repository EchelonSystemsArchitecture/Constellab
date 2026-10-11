/**
 * ConstellaLab desktop shell (Electron).
 *
 * Day 1: launches the local Python core service and hosts the frontend.
 * In development it starts vite's dev server; in the packaged .exe it serves
 * the prebuilt frontend and runs the embedded Python interpreter, so the
 * application is fully self-contained and reproducible on Windows.
 */
const { app, BrowserWindow, dialog } = require("electron");
const fs = require("fs");
const http = require("http");
const path = require("path");
const { spawn } = require("child_process");

const CORE_PORT = 8765;
const DEV_SERVER_URL = "http://localhost:5173";
const CORE_URL = `http://127.0.0.1:${CORE_PORT}`;

function appDir() {
  if (!app.isPackaged) return path.join(__dirname, "..", "..");
  return process.resourcesPath;
}

function waitForCore(url, timeoutMs = 20000) {
  const deadline = Date.now() + timeoutMs;
  return new Promise((resolve, reject) => {
    const tick = () => {
      const req = http.get(`${url}/api/health`, (res) => {
        res.resume();
        res.on("end", () => resolve(true));
      });
      req.on("error", () => {
        if (Date.now() > deadline) reject(new Error("core service did not become ready"));
        else setTimeout(tick, 250);
      });
    };
    tick();
  });
}

function startCore() {
  const dir = appDir();
  let pythonExe;
  let cwd;
  if (app.isPackaged) {
    pythonExe = path.join(process.resourcesPath, "app.asar.unpacked", "python", "python.exe");
    cwd = path.join(process.resourcesPath, "app.asar.unpacked", "python");
  } else {
    pythonExe = "python";
    cwd = path.join(dir, "core");
  }
  console.log(`[ConstellaLab] Starting core with python: ${pythonExe}, cwd: ${cwd}`);
  console.log(`[ConstellaLab] Python exists: ${fs.existsSync(pythonExe)}`);
  const child = spawn(pythonExe, ["-m", "constellab_core", "serve", "--port", String(CORE_PORT)], {
    cwd,
    env: { ...process.env, PYTHONIOENCODING: "utf-8", PYTHONPATH: cwd },
    windowsHide: true,
  });
  child.stdout.on("data", (d) => process.stdout.write(`[core] ${d}`));
  child.stderr.on("data", (d) => process.stderr.write(`[core] ${d}`));
  child.on("error", (err) => {
    console.error(`[ConstellaLab] Failed to spawn Python: ${err}`);
  });
  return child;
}

async function createWindow() {
  const win = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 960,
    minHeight: 600,
    title: "ConstellaLab — Orbital Test Lab",
    backgroundColor: "#0b0e14",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  win.setMenuBarVisibility(false);

  if (app.isPackaged) {
    await win.loadFile(path.join(process.resourcesPath, "app.asar.unpacked", "frontend", "dist", "index.html"));
  } else {
    await win.loadURL(DEV_SERVER_URL);
  }
  return win;
}

app.whenReady().then(async () => {
  const core = startCore();
  app.coreChild = core;
  try {
    await waitForCore(CORE_URL);
  } catch (err) {
    dialog.showErrorBox("ConstellaLab core failed to start", String(err));
    app.quit();
    return;
  }
  await createWindow();
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

app.on("before-quit", () => {
  if (app.coreChild && !app.coreChild.killed) {
    app.coreChild.kill();
  }
});
