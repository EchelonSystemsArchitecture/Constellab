/**
 * Locate a usable Python 3 interpreter and (when run directly) exec it with
 * PYTHONPATH pointing at ./core, so `node scripts/py.js -m constellab_core status`
 * works on Windows (`python`) and on Linux/macOS (`python3`) alike.
 */
const { spawnSync } = require("child_process");
const path = require("path");

const CORE_DIR = path.join(__dirname, "..", "core");

function pythonCommand() {
  for (const cmd of ["python", "python3"]) {
    const res = spawnSync(cmd, ["-c", "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)"], {
      stdio: "ignore",
    });
    if (!res.error && res.status === 0) return cmd;
  }
  throw new Error("Python >= 3.10 not found on PATH (tried `python`, `python3`)");
}

function pythonEnv(extra = {}) {
  const sep = process.platform === "win32" ? ";" : ":";
  const existing = process.env.PYTHONPATH ? sep + process.env.PYTHONPATH : "";
  return { ...process.env, PYTHONIOENCODING: "utf-8", PYTHONPATH: CORE_DIR + existing, ...extra };
}

module.exports = { pythonCommand, pythonEnv, CORE_DIR };

if (require.main === module) {
  const res = spawnSync(pythonCommand(), process.argv.slice(2), { stdio: "inherit", env: pythonEnv() });
  process.exit(res.status ?? 1);
}
