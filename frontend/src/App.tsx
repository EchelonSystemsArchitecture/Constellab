import { useCallback, useEffect, useState } from "react";
import { ContractError, SCHEMA_VERSION, SimulationSnapshot, parseSnapshot } from "./contract";
import { LoadingScreen } from "./LoadingScreen";
import { SceneShell } from "./scene/SceneShell";

interface CoreStatus {
  name: string;
  version: string;
  schema_version: string;
  status: string;
}

const CORE_URL = "http://127.0.0.1:8765";

type SnapshotState =
  | { kind: "loading" }
  | { kind: "ready"; snapshot: SimulationSnapshot }
  | { kind: "rejected"; reason: string; errors: { path: string; message: string }[] };

async function fetchJson(path: string): Promise<unknown> {
  const res = await fetch(`${CORE_URL}${path}`);
  if (!res.ok) throw new Error(`core returned HTTP ${res.status} for ${path}`);
  return res.json();
}

export default function App() {
  const [showLoading, setShowLoading] = useState(true);
  const [status, setStatus] = useState<CoreStatus | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [snapshot, setSnapshot] = useState<SnapshotState>({ kind: "loading" });

  const handleLoadingDone = useCallback(() => {
    setShowLoading(false);
  }, []);

  useEffect(() => {
    if (showLoading) return;
    let cancelled = false;
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
    fetchJson("/api/snapshot")
      .then((data) => {
        if (cancelled) return;
        setSnapshot({ kind: "ready", snapshot: parseSnapshot(data) });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof ContractError) {
          setSnapshot({ kind: "rejected", reason: "snapshot rejected by contract", errors: err.errors });
        } else {
          setSnapshot({ kind: "rejected", reason: err instanceof Error ? err.message : String(err), errors: [] });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [showLoading]);

  if (showLoading) {
    return <LoadingScreen onReady={handleLoadingDone} />;
  }

  return (
    <div className="app">
      <header className="app__header">
        <span className="app__brand">ConstellaLab</span>
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
        Day 3 — offline Earth viewport · core-owned snapshots (contract v{SCHEMA_VERSION}) · no
        orbital motion or inter-satellite communication yet
      </footer>
    </div>
  );
}

export type { SnapshotState };
