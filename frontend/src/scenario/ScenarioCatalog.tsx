import { useCallback, useEffect, useState } from "react";
import type { SimulationConfig } from "../contract";
import { CoreError, listScenarios, loadScenario, type ScenarioSummary } from "./api";

interface ScenarioCatalogProps {
  activeScenarioId?: string | null;
  /** Called after the core accepted the load (clock restarted at t=0). */
  onLoaded?: (scenario: SimulationConfig) => void;
  /** Called after load; dashboard uses it to enter the simulator. */
  onLaunch?: () => void;
}

export function ScenarioCatalog({ activeScenarioId, onLoaded, onLaunch }: ScenarioCatalogProps) {
  const [scenarios, setScenarios] = useState<ScenarioSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pendingKey, setPendingKey] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<{ key: string; message: string } | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const catalog = await listScenarios();
      setScenarios(catalog.scenarios);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const handleLoad = async (key: string) => {
    setPendingKey(key);
    setLoadError(null);
    try {
      const loaded = await loadScenario(key);
      onLoaded?.(loaded.scenario);
      onLaunch?.();
    } catch (err) {
      const message = err instanceof CoreError && err.errors.length > 0
        ? err.errors.map((e) => `${e.path}: ${e.message}`).join(" · ")
        : err instanceof Error ? err.message : String(err);
      setLoadError({ key, message });
    } finally {
      setPendingKey(null);
    }
  };

  if (loading) {
    return (
      <div className="catalog-state">
        <span className="loading-screen__spinner" /> reading scenario catalog from core…
      </div>
    );
  }

  if (error) {
    return (
      <div className="catalog-state catalog-state--error" role="alert">
        <div className="catalog-state__title">CORE UNREACHABLE</div>
        <p className="mono">{error}</p>
        <p>Start the core (or `npm run dev`) and retry. Scenarios are served by the core, never hard-coded here.</p>
        <button type="button" className="startup-btn startup-btn--ghost" onClick={() => void refresh()}>
          RETRY
        </button>
      </div>
    );
  }

  return (
    <div className="scenarios-grid">
      {scenarios.map((scenario) => {
        const active = scenario.scenario_id === activeScenarioId;
        const pending = pendingKey === scenario.key;
        const failed = loadError?.key === scenario.key;
        return (
          <div
            key={scenario.key}
            className={`scenario-card ${active ? "scenario-card--active" : ""}`}
            data-scenario-key={scenario.key}
          >
            <div className={`scenario-card__badge ${active ? "" : "scenario-card__badge--neutral"}`}>
              {active ? "ACTIVE" : scenario.key.toUpperCase()}
            </div>
            <h3 className="scenario-card__title">{scenario.name}</h3>
            <p className="scenario-card__desc mono">
              {scenario.scenario_id} · validated SimulationConfig v1.0.0
            </p>
            <div className="scenario-card__meta">
              <span>SATELLITES: {scenario.satellites}</span>
              <span>EPOCH: {scenario.epoch_utc}</span>
              <span>SCALE: ×{scenario.time_scale}</span>
            </div>
            {failed && (
              <div className="scenario-card__error mono" role="alert">
                LOAD REJECTED — {loadError.message}
              </div>
            )}
            <button
              type="button"
              className={`startup-btn ${active ? "startup-btn--ghost" : "startup-btn--primary"} scenario-card__launch-btn`}
              onClick={() => void handleLoad(scenario.key)}
              disabled={pending}
              data-testid={`load-${scenario.key}`}
            >
              {pending ? "LOADING…" : active ? "RESTART THIS SCENARIO" : "LOAD SCENARIO"}
            </button>
          </div>
        );
      })}
      {scenarios.length === 0 && (
        <div className="catalog-state">The core exposes no built-in scenarios.</div>
      )}
    </div>
  );
}
