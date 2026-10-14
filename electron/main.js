const { app, BrowserWindow, dialog, Menu, shell } = require("electron");
const fs = require("fs");
const http = require("http");
const path = require("path");
const { spawn } = require("child_process");

const CORE_PORT = 8765;
const DEV_SERVER_URL = "http://localhost:5173";
const CORE_URL = `http://127.0.0.1:${CORE_PORT}`;
const APP_ICON = path.join(__dirname, "..", "assets", "icons", process.platform === "win32" ? "icon.ico" : "icon.png");

function appDir() {
  if (!app.isPackaged) return path.join(__dirname, "..");
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
    pythonExe = require("../scripts/py").pythonCommand();
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
  child.on("exit", (code, signal) => {
    console.log(`[ConstellaLab] core exited (code ${code}, signal ${signal})`);
  });
  return child;
}

/**
 * Reuse a core that is already listening (e.g. one started by scripts/dev.js)
 * instead of spawning a second copy that cannot bind the fixed port.
 */
async function ensureCore() {
  try {
    await waitForCore(CORE_URL, 1200);
    console.log(`[ConstellaLab] Reusing core already listening on ${CORE_URL}`);
    return null;
  } catch {
    console.log("[ConstellaLab] No local core yet; starting one");
  }
  const child = startCore();
  await waitForCore(CORE_URL);
  return child;
}

function createMenu() {
  const template = [
    {
      label: "File",
      submenu: [
        { role: "quit" }
      ]
    },
    {
      label: "View",
      submenu: [
        { role: "reload" },
        { role: "toggleDevTools" },
        { type: "separator" },
        { role: "resetZoom" },
        { role: "zoomIn" },
        { role: "zoomOut" },
        { type: "separator" },
        { role: "togglefullscreen" }
      ]
    },
    {
      label: "Help",
      submenu: [
        {
          label: "ConstellaLab v" + app.getVersion(),
          enabled: false
        }
      ]
    }
  ];
  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

async function createWindow() {
  const win = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 960,
    minHeight: 600,
    title: "ConstellaLab",
    // Matches the white startup splash so the first visible frame is not a dark flash.
    backgroundColor: "#ffffff",
    icon: APP_ICON,
    frame: true,
    show: false,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
  });

  win.once("ready-to-show", () => {
    win.show();
  });

  win.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: "deny" };
  });

  win.webContents.on("context-menu", (event, params) => {
    if (params.isEditable || params.selectionText) {
      return;
    }
    event.preventDefault();
  });

  if (app.isPackaged) {
    await win.loadFile(path.join(process.resourcesPath, "app.asar.unpacked", "frontend", "dist", "index.html"));
  } else {
    await win.loadURL(DEV_SERVER_URL);
  }
  return win;
}

app.whenReady().then(async () => {
  createMenu();
  try {
    app.coreChild = await ensureCore();
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
