import { useCallback, useEffect, useState } from "react";
import { ContractError, SCHEMA_VERSION, SimulationSnapshot, parseSnapshot } from "./contract";
import { SceneShell } from "./scene/SceneShell";
import { StartupScreen } from "./StartupScreen";

interface CoreStatus {
  name: string;
  version: string;
  schema_version: string;
  status: string;
}

const CORE_URL = "http://127.0.0.1:8765";
const SNAPSHOT_POLL_MS = 200;
const STATUS_POLL_MS = 2000;

type SnapshotState =
  | { kind: "loading" }
  | { kind: "ready"; snapshot: SimulationSnapshot }
  | { kind: "rejected"; reason: string; errors: { path: string; message: string }[] };

async function fetchJson(path: string): Promise<unknown> {
  const res = await fetch(`${CORE_URL}${path}`);
  if (!res.ok) throw new Error(`core returned HTTP ${res.status} for ${path}`);
  return res.json();
}

function describeFailure(err: unknown): SnapshotState {
  if (err instanceof ContractError) {
    return { kind: "rejected", reason: "snapshot rejected by contract", errors: err.errors };
  }
  return { kind: "rejected", reason: err instanceof Error ? err.message : String(err), errors: [] };
}

export default function App() {
  const [phase, setPhase] = useState<"startup" | "app">("startup");
  const [status, setStatus] = useState<CoreStatus | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [snapshot, setSnapshot] = useState<SnapshotState>({ kind: "loading" });

  const handleLaunch = useCallback(() => setPhase("app"), []);

  useEffect(() => {
    let cancelled = false;
    const poll = () => {
      fetchJson("/api/status")
        .then((data) => {
          if (cancelled) return;
          setStatus(data as CoreStatus);
          setStatusError(null);
        })
        .catch((err: Error) => {
          if (cancelled) return;
          setStatus(null);
          setStatusError(err.message);
        });
    };
    poll();
    const timer = window.setInterval(poll, STATUS_POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  // Only the core advances simulation time; the renderer polls its snapshots.
  // A self-scheduling timeout keeps one request in flight at a time.
  useEffect(() => {
    if (phase !== "app") return;
    let cancelled = false;
    let timer: number | undefined;
    const poll = async () => {
      try {
        const data = await fetchJson("/api/snapshot");
        if (!cancelled) setSnapshot({ kind: "ready", snapshot: parseSnapshot(data) });
      } catch (err) {
        if (!cancelled) setSnapshot((prev) => (prev.kind === "ready" ? prev : describeFailure(err)));
      } finally {
        if (!cancelled) timer = window.setTimeout(poll, SNAPSHOT_POLL_MS);
      }
    };
    poll();
    return () => {
      cancelled = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [phase]);

  if (phase === "startup") {
    return <StartupScreen onLaunch={handleLaunch} />;
  }

  return (
    <div className="app">
      <header className="app__header">
        <span className="app__brand">
          <img className="app__brand-mark" src="constellab-symbol.svg" alt="" />
          ConstellaLab
        </span>
        <span className="app__tagline">software-only crash-test lab for satellite swarms</span>
        <span
          className={`app__status ${status ? "app__status--ok" : "app__status--down"}`}
          data-testid="core-status"
        >
          {status
            ? `core ${status.name} v${status.version} (schema ${status.schema_version}) — ${status.status}`
            : statusError
              ? `core unreachable: ${statusError}`
              : "connecting to core…"}
        </span>
      </header>
      <main className="app__main">
        <SceneShell snapshot={snapshot} />
      </main>
      <footer className="app__footer">
        Day 5 — deterministic two-body orbits · core-owned snapshots (contract v{SCHEMA_VERSION}) · no
        inter-satellite communication yet
      </footer>
    </div>
  );
}

export type { SnapshotState };
