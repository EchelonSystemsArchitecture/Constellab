import { useCallback, useEffect, useRef, useState } from "react";
import { ContractError, SimulationSnapshot } from "./contract";
import { cursorOf, parseStateEnvelope, shouldAcceptState, type StateCursor } from "./api/state";
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

let requestCounter = 0;

/** The canonical state stream; the request id lets a reply be traced in core logs. */
async function fetchState() {
  const requestId = `ui-${Date.now().toString(36)}-${(requestCounter++).toString(36)}`;
  const res = await fetch(`${CORE_URL}/api/state`, { headers: { "X-Request-Id": requestId } });
  if (!res.ok) throw new Error(`core returned HTTP ${res.status} for /api/state`);
  return parseStateEnvelope(await res.json());
}

function describeFailure(err: unknown): SnapshotState {
  if (err instanceof ContractError) {
    return { kind: "rejected", reason: "snapshot rejected by contract", errors: err.errors };
  }
  return { kind: "rejected", reason: err instanceof Error ? err.message : String(err), errors: [] };
}

export default function App() {
  const [phase, setPhase] = useState<"startup" | "app">(() => {
    if (typeof window !== "undefined") {
      const p = new URLSearchParams(window.location.search).get("phase");
      if (p === "app") return "app";
    }
    return "startup";
  });
  const [status, setStatus] = useState<CoreStatus | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [snapshot, setSnapshot] = useState<SnapshotState>({ kind: "loading" });
  // Highest state revision applied so far; late replies are dropped against it.
  const cursor = useRef<StateCursor | null>(null);

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

  // Only the core advances simulation time; the renderer polls the canonical
  // state stream. A self-scheduling timeout keeps one request in flight at a
  // time, and the revision guard makes an out-of-order reply a no-op.
  useEffect(() => {
    if (phase !== "app") return;
    let cancelled = false;
    let timer: number | undefined;
    const poll = async () => {
      try {
        const state = await fetchState();
        if (cancelled) return;
        if (!shouldAcceptState(cursor.current, state)) return;
        cursor.current = cursorOf(state);
        setSnapshot({ kind: "ready", snapshot: state.snapshot });
      } catch (err) {
        if (!cancelled) setSnapshot((prev) => (prev.kind === "ready" ? prev : describeFailure(err)));
      } finally {
        // Never reschedule after cleanup, or an unmounted tab keeps polling.
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
    <div className="app app--tactical">
      <main className="app__main app__main--tactical">
        <SceneShell
          snapshot={snapshot}
          status={status}
          statusError={statusError}
          onExit={() => setPhase("startup")}
        />
      </main>
    </div>
  );
}

export type { SnapshotState };
