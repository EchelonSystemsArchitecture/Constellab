import { ConstellabSymbol } from "./ConstellabSymbol";

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
            <div className="scenarios-grid">
              <div className="scenario-card scenario-card--active">
                <div className="scenario-card__badge">PRIMARY BENCHMARK</div>
                <h3 className="scenario-card__title">Four Satellite Constellation</h3>
                <p className="scenario-card__desc">
                  LEO Walker-delta swarm with deterministic two-body propagation. Tests inter-agent proximity, collision avoidance corridors, and orbital synchronization.
                </p>
                <div className="scenario-card__meta">
                  <span>SATELLITES: 4</span>
                  <span>ALTITUDE: 550 KM</span>
                  <span>EPOCH: 2026-03-01</span>
                </div>
                <button
                  type="button"
                  className="startup-btn startup-btn--primary scenario-card__launch-btn"
                  onClick={() => {
                    onClose();
                    onLaunch();
                  }}
                >
                  LAUNCH THIS SCENARIO
                </button>
              </div>

              <div className="scenario-card">
                <div className="scenario-card__badge scenario-card__badge--neutral">STANDBY</div>
                <h3 className="scenario-card__title">Empty Orbit Ground Truth</h3>
                <p className="scenario-card__desc">
                  Baseline zero-satellite environment for validating solar radiation pressure models, gravitational harmonics (J2), and coordinate frame calibration.
                </p>
                <div className="scenario-card__meta">
                  <span>SATELLITES: 0</span>
                  <span>FRAME: ECI / J2000</span>
                  <span>MODE: CALIBRATION</span>
                </div>
                <button
                  type="button"
                  className="startup-btn startup-btn--ghost scenario-card__launch-btn"
                  onClick={() => {
                    onClose();
                    onLaunch();
                  }}
                >
                  LAUNCH CALIBRATION
                </button>
              </div>
            </div>
          ) : (
            <div className="evidence-panel">
              <div className="evidence-metrics">
                <div className="evidence-metric-card">
                  <span className="metric-label">CONTRACT SPEC</span>
                  <span className="metric-val">v0.1.0 (ECI Frame)</span>
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
                  <span className="log-text">Core physics bridge validated. Contract schema v0.1.0 synchronized.</span>
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
