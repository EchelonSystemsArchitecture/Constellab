/**
 * Day 13: end-to-end harness.
 *
 * The suite drives the *real* Python core over its HTTP API with the *real*
 * client modules (envelope parsing, revision guard, selection, inspector,
 * ground-track maths). Only WebGL is out of scope: there is no headless GPU
 * here, so the 3D draw is verified in the app and its batching path is covered
 * by `npm run bench:fleet` plus the scene tests.
 */
import { spawn, spawnSync, type ChildProcessWithoutNullStreams } from "node:child_process";
import { existsSync, readFileSync, rmSync } from "node:fs";
import os from "node:os";
import path from "node:path";

export interface CoreHandle {
  baseUrl: string;
  port: number;
  stop: () => Promise<void>;
}

export interface CoreResponse<T = unknown> {
  status: number;
  headers: Headers;
  body: T;
}

/** Walk up until the repository root (identified by the core package) is found. */
export function repoRoot(start = __dirname): string {
  let directory = start;
  for (let i = 0; i < 10; i++) {
    if (existsSync(path.join(directory, "core", "constellab_core", "service.py"))) return directory;
    const parent = path.dirname(directory);
    if (parent === directory) break;
    directory = parent;
  }
  throw new Error(`repository root not found above ${start}`);
}

function pythonCommand(): string {
  for (const candidate of ["python", "python3"]) {
    const probe = spawnSync(candidate, ["-c", "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)"], {
      encoding: "utf8",
    });
    if (!probe.error && probe.status === 0) return candidate;
  }
  throw new Error("Python >= 3.10 not found on PATH (tried python, python3)");
}

/** Start a real core on an ephemeral port and resolve once it prints its URL. */
export async function startCore(scenario = "visual-orbit-demo", timeoutMs = 15_000): Promise<CoreHandle> {
  const root = repoRoot();
  const coreDir = path.join(root, "core");
  const separator = process.platform === "win32" ? ";" : ":";
  const child: ChildProcessWithoutNullStreams = spawn(
    pythonCommand(),
    ["-m", "constellab_core", "serve", "--port", "0", "--scenario", scenario],
    {
      cwd: coreDir,
      env: {
        ...process.env,
        PYTHONPATH: coreDir + (process.env.PYTHONPATH ? separator + process.env.PYTHONPATH : ""),
        PYTHONIOENCODING: "utf-8",
      },
    },
  );

  const port = await new Promise<number>((resolve, reject) => {
    let buffered = "";
    const timer = setTimeout(() => {
      child.kill();
      reject(new Error(`core did not report a port within ${timeoutMs} ms: ${buffered}`));
    }, timeoutMs);
    const onData = (chunk: Buffer) => {
      buffered += chunk.toString();
      const match = /listening on http:\/\/127\.0\.0\.1:(\d+)/.exec(buffered);
      if (match) {
        clearTimeout(timer);
        resolve(Number(match[1]));
      }
    };
    child.stdout.on("data", onData);
    child.stderr.on("data", (chunk: Buffer) => {
      buffered += chunk.toString();
    });
    child.once("exit", (code) => {
      clearTimeout(timer);
      reject(new Error(`core exited with ${code}: ${buffered}`));
    });
    child.once("error", (error) => {
      clearTimeout(timer);
      reject(error);
    });
  });

  return {
    port,
    baseUrl: `http://127.0.0.1:${port}`,
    stop: () => new Promise<void>((resolve) => {
      if (child.exitCode !== null) {
        resolve();
        return;
      }
      child.once("exit", () => resolve());
      child.kill();
      setTimeout(() => {
        if (child.exitCode === null) child.kill("SIGKILL");
        resolve();
      }, 3000).unref();
    }),
  };
}

export async function requestJson<T = unknown>(
  baseUrl: string,
  method: "GET" | "POST",
  route: string,
  body?: unknown,
  headers: Record<string, string> = {},
): Promise<CoreResponse<T>> {
  const response = await fetch(`${baseUrl}${route}`, {
    method,
    headers: { ...(body === undefined ? {} : { "Content-Type": "application/json" }), ...headers },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const text = await response.text();
  let parsed: unknown = null;
  try {
    parsed = text.length > 0 ? JSON.parse(text) : null;
  } catch {
    parsed = text;
  }
  return { status: response.status, headers: response.headers, body: parsed as T };
}

export const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

/** Run a scenario headlessly and return its NDJSON records, without a server. */
export function runHeadless(scenario: string, duration = 60, step = 10): string {
  const root = repoRoot();
  const coreDir = path.join(root, "core");
  const separator = process.platform === "win32" ? ";" : ":";
  const out = path.join(os.tmpdir(), `constellab-e2e-${process.pid}-${Math.random().toString(36).slice(2)}.ndjson`);
  try {
    const result = spawnSync(
      pythonCommand(),
      ["-m", "constellab_core", "run", scenario, "--duration", String(duration), "--step", String(step), "--out", out],
      {
        cwd: coreDir,
        env: {
          ...process.env,
          PYTHONPATH: coreDir + (process.env.PYTHONPATH ? separator + process.env.PYTHONPATH : ""),
          PYTHONIOENCODING: "utf-8",
        },
        encoding: "utf8",
        maxBuffer: 64 * 1024 * 1024,
      },
    );
    if (result.error || result.status !== 0) {
      throw new Error(`headless run failed: ${result.error ?? result.stderr}`);
    }
    return readFileSync(out, "utf8");
  } finally {
    rmSync(out, { force: true });
  }
}
