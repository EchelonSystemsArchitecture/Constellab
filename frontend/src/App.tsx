import { useEffect, useState } from "react";
import { SceneShell } from "./scene/SceneShell";

interface CoreStatus {
  name: string;
  version: string;
  schema_version: number;
  status: string;
  python_version: string;
  platform: string;
}

const CORE_URL = "http://127.0.0.1:8765";

export default function App() {
  const [status, setStatus] = useState<CoreStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch(`${CORE_URL}/api/status`)
      .then((res) => {
        if (!res.ok) throw new Error(`core returned HTTP ${res.status}`);
        return res.json();
      })
      .then((data: CoreStatus) => {
        if (!cancelled) {
          setStatus(data);
          setError(null);
        }
      })
      .catch((err: Error) => {
        if (!cancelled) {
          setStatus(null);
          setError(err.message);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

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
            : error
              ? `core unreachable: ${error}`
              : "connecting to core…"}
        </span>
      </header>
      <main className="app__main">
        <SceneShell />
      </main>
      <footer className="app__footer">
        Day 1 baseline — no inter-satellite communication yet
      </footer>
    </div>
  );
}
