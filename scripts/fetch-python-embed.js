/**
 * Fetches the official embedded Python distribution for Windows and unpacks
 * it into ./python so the packaged .exe is self-contained (no system Python
 * required). Idempotent: skips the download when already present. Works on
 * Windows (PowerShell) and on Linux/macOS cross-build hosts (python zipfile).
 *
 * Tries the newest 3.14.x embed first, then falls back to 3.12.x.
 */
const fs = require("fs");
const https = require("https");
const path = require("path");
const { execFileSync } = require("child_process");
const { pythonCommand } = require("./py");

const OUT_DIR = path.join(__dirname, "..", "python");
const CORE_SRC = path.join(__dirname, "..", "core");
const VERSIONS = [
  { dir: "3.14.1", zip: "python-3.14.1-embed-amd64.zip" },
  { dir: "3.12.8", zip: "python-3.12.8-embed-amd64.zip" },
];

function download(url, dest) {
  return new Promise((resolve, reject) => {
    const file = fs.createWriteStream(dest);
    https
      .get(url, (res) => {
        if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
          file.close();
          fs.unlinkSync(dest);
          return download(res.headers.location, dest).then(resolve, reject);
        }
        if (res.statusCode !== 200) {
          file.close();
          fs.unlinkSync(dest);
          return reject(new Error(`HTTP ${res.statusCode} for ${url}`));
        }
        res.pipe(file);
        file.on("finish", () => file.close(resolve));
      })
      .on("error", (err) => {
        fs.unlinkSync(dest);
        reject(err);
      });
  });
}

function extractZip(zip, dest) {
  if (process.platform === "win32") {
    execFileSync("powershell", [
      "-NoProfile",
      "-Command",
      `Expand-Archive -LiteralPath '${zip}' -DestinationPath '${dest}' -Force`,
    ]);
    return;
  }
  // Linux/macOS build hosts: Python's zipfile module is always available.
  execFileSync(pythonCommand(), ["-m", "zipfile", "-e", zip, dest]);
}

function syncCore() {
  // Always refresh: the packaged exe runs the core from python/core, so a stale
  // copy would silently ship old code even when the interpreter is cached.
  const pthFile = fs.readdirSync(OUT_DIR).find((f) => /^python\d+\._pth$/.test(f));
  if (pthFile) {
    const pthPath = path.join(OUT_DIR, pthFile);
    const content = fs.readFileSync(pthPath, "utf8");
    if (!content.includes("./core")) fs.appendFileSync(pthPath, "./core\n");
  }
  const coreDst = path.join(OUT_DIR, "core");
  fs.rmSync(coreDst, { recursive: true, force: true });
  fs.cpSync(CORE_SRC, coreDst, {
    recursive: true,
    filter: (src) => !/(^|[\\/])(__pycache__|tests)([\\/]|$)/.test(path.relative(CORE_SRC, src)),
  });
  console.log("[fetch-python] core synced into python/core");
}

async function ensureInterpreter() {
  const marker = path.join(OUT_DIR, "python.exe");
  if (fs.existsSync(marker)) {
    console.log("[fetch-python] embedded python already present, skipping download");
    return;
  }
  fs.mkdirSync(OUT_DIR, { recursive: true });
  const tmpZip = path.join(OUT_DIR, "_embed.zip");
  let lastErr;
  for (const v of VERSIONS) {
    const url = `https://www.python.org/ftp/python/${v.dir}/${v.zip}`;
    try {
      console.log(`[fetch-python] downloading ${url}`);
      await download(url, tmpZip);
      extractZip(tmpZip, OUT_DIR);
      fs.unlinkSync(tmpZip);
      if (!fs.existsSync(marker)) throw new Error("python.exe missing after extraction");
      console.log(`[fetch-python] embedded python ${v.dir} ready`);
      return;
    } catch (err) {
      lastErr = err;
      console.warn(`[fetch-python] ${v.dir} failed: ${err.message}`);
    }
  }
  throw lastErr;
}

async function main() {
  await ensureInterpreter();
  syncCore();
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
