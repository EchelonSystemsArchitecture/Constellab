/**
 * Fetches the official embedded Python distribution for Windows and unpacks
 * it into ./python so the packaged .exe is self-contained (no system Python
 * required). Idempotent: skips the download when already present.
 *
 * Tries the newest 3.14.x embed first, then falls back to 3.12.x.
 */
const fs = require("fs");
const https = require("https");
const path = require("path");
const { execFileSync } = require("child_process");

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

async function main() {
  const marker = path.join(OUT_DIR, "python.exe");
  if (fs.existsSync(marker)) {
    console.log("[fetch-python] embedded python already present, skipping");
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
      execFileSync("powershell", [
        "-NoProfile",
        "-Command",
        `Expand-Archive -LiteralPath '${tmpZip}' -DestinationPath '${OUT_DIR}' -Force`,
      ]);
      fs.unlinkSync(tmpZip);
      if (!fs.existsSync(marker)) throw new Error("python.exe missing after extraction");

      const pthFile = path.join(OUT_DIR, "python314._pth");
      if (fs.existsSync(pthFile)) {
        const content = fs.readFileSync(pthFile, "utf8");
        if (!content.includes("./core")) {
          fs.appendFileSync(pthFile, "./core\n");
        }
      }

      const coreDst = path.join(OUT_DIR, "core");
      if (fs.existsSync(coreDst)) {
        fs.rmSync(coreDst, { recursive: true, force: true });
      }
      fs.mkdirSync(coreDst, { recursive: true });
      for (const item of fs.readdirSync(CORE_SRC)) {
        const src = path.join(CORE_SRC, item);
        const dst = path.join(coreDst, item);
        if (fs.statSync(src).isDirectory()) {
          fs.cpSync(src, dst, { recursive: true });
        } else {
          fs.copyFileSync(src, dst);
        }
      }

      console.log("[fetch-python] embedded python ready");
      return;
    } catch (err) {
      lastErr = err;
      console.warn(`[fetch-python] ${v.dir} failed: ${err.message}`);
    }
  }
  throw lastErr;
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
