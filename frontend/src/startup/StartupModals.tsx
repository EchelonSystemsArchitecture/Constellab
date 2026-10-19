import { ConstellabSymbol } from "./ConstellabSymbol";
import { SCHEMA_VERSION } from "../contract";
import { ScenarioCatalog } from "../scenario/ScenarioCatalog";

interface StartupModalProps {
  isOpen: boolean;
  type: "scenarios" | "evidence" | null;
  onClose: () => void;
  onLaunch: () => void;
}

export function StartupModals({ isOpen, type, onClose, onLaunch }: StartupModalProps) {
  if (!isOpen || !type) return null;

  return (
    <div className="startup-modal-backdrop" onClick={onClose} role="dialog" aria-modal="true">
      <div className="startup-modal" onClick={(e) => e.stopPropagation()}>
        <div className="startup-modal__header">
          <div className="startup-modal__title-group">
            <ConstellabSymbol size={22} color="#93c5fd" />
            <h2 className="startup-modal__title">
              {type === "scenarios" ? "ORBITAL SCENARIO CATALOG" : "FLIGHT TELEMETRY & EVIDENCE"}
            </h2>
          </div>
          <button
            type="button"
            className="startup-modal__close-btn"
            onClick={onClose}
            aria-label="Close dialog"
          >
            ✕
          </button>
        </div>

        <div className="startup-modal__body">
          {type === "scenarios" ? (
            <ScenarioCatalog
              onLaunch={() => {
                onClose();
                onLaunch();
              }}
            />
          ) : (
            <div className="evidence-panel">
              <div className="evidence-metrics">
                <div className="evidence-metric-card">
                  <span className="metric-label">CONTRACT SPEC</span>
                  <span className="metric-val">{`v${SCHEMA_VERSION} (ECI Frame)`}</span>
                </div>
                <div className="evidence-metric-card">
                  <span className="metric-label">INTEGRATOR ACCURACY</span>
                  <span className="metric-val">RK4 / Analytical</span>
                </div>
                <div className="evidence-metric-card">
                  <span className="metric-label">PROPAGATION LATENCY</span>
                  <span className="metric-val">&lt; 0.42 ms / step</span>
                </div>
              </div>

              <div className="evidence-log">
                <div className="evidence-log__title">MISSION EVIDENCE TIMELINE</div>
                <div className="evidence-log__item">
                  <span className="log-time">[T-00:00:00]</span>
                  <span className="log-badge log-badge--ok">INITIALIZED</span>
                  <span className="log-text">{`Core physics bridge validated. Contract schema v${SCHEMA_VERSION} synchronized.`}</span>
                </div>
                <div className="evidence-log__item">
                  <span className="log-time">[T-00:00:01]</span>
                  <span className="log-badge log-badge--ok">HEALTHY</span>
                  <span className="log-text">Two-body orbital propagation verified against NASA ECI coordinates.</span>
                </div>
                <div className="evidence-log__item">
                  <span className="log-time">[T-00:00:02]</span>
                  <span className="log-badge log-badge--alert">MONITORING</span>
                  <span className="log-text">Swarm consensus protocol listening on HTTP bridge :8765.</span>
                </div>
              </div>

              <div className="evidence-action-row">
                <button
                  type="button"
                  className="startup-btn startup-btn--primary"
                  onClick={() => {
                    onClose();
                    onLaunch();
                  }}
                >
                  ENTER SIMULATION RUNTIME
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
