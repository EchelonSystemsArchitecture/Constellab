import { useEffect, useMemo, useState } from "react";
import type { SimulationSnapshot } from "../contract";
import { SCENE_CONFIG } from "./config";
import type { DiagnosticToggles } from "./diagnostics";
import { diagnosticsModel, visibleLabelIds } from "./diagnostics";
import type { SatelliteProjection } from "./EarthScene";

const TOGGLE_DEFS: { key: keyof DiagnosticToggles; label: string; hint: string }[] = [
  { key: "ids", label: "IDS", hint: "Satellite id labels near markers (bounded)" },
  { key: "orbitPlane", label: "PLANE", hint: "Translucent orbital-plane fill for the selection" },
  { key: "simTime", label: "SIM TIME", hint: "Simulated UTC and elapsed time" },
  { key: "selectedPosition", label: "POSITION", hint: "Selected satellite ECI position and altitude" },
  { key: "snapshotAge", label: "AGE", hint: "Age of the last accepted snapshot" },
];

interface SceneDiagnosticsProps {
  snapshot: SimulationSnapshot | null;
  projections: SatelliteProjection[];
  toggles: DiagnosticToggles;
  selectedId: string | null;
  receivedAtMs: number | null;
  renderFps: number | null;
  onToggle: (key: keyof DiagnosticToggles) => void;
  onClose: () => void;
}

export function SceneDiagnostics({
  snapshot,
  projections,
  toggles,
  selectedId,
  receivedAtMs,
  renderFps,
  onToggle,
  onClose,
}: SceneDiagnosticsProps) {
  const [nowMs, setNowMs] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNowMs(Date.now()), SCENE_CONFIG.diagnostics.refreshMs);
    return () => window.clearInterval(timer);
  }, []);

  const model = useMemo(
    () => diagnosticsModel({
      snapshot,
      toggles,
      receivedAtMs,
      nowMs,
      renderFps,
      selectedId,
      fleetSatellites: snapshot?.satellites.length ?? null,
    }),
    [snapshot, toggles, receivedAtMs, nowMs, renderFps, selectedId],
  );

  const labelIds = useMemo(
    () => new Set(visibleLabelIds(projections, toggles, selectedId)),
    [projections, toggles, selectedId],
  );

  return (
    <>
      {/* ID labels are DOM, not 3D text: they stay crisp at any zoom and cost
          nothing when the overlay is off. */}
      {toggles.ids && (
        <div className="diagnostic-labels" data-testid="diagnostic-labels" aria-hidden="true">
          {projections
            .filter((projection) => labelIds.has(projection.id) && !projection.isOccluded)
            .map((projection) => (
              <span
                key={projection.id}
                className={`diagnostic-label mono ${projection.id === selectedId ? "diagnostic-label--selected" : ""}`}
                data-satellite-label={projection.id}
                style={{ left: `${projection.screenX + 8}px`, top: `${projection.screenY - 14}px`, color: projection.colorHex }}
              >
                {projection.id}
              </span>
            ))}
        </div>
      )}

      <aside
        className="scene-shell__diagnostics"
        aria-label="Visual diagnostics"
        data-testid="diagnostics"
        data-snapshot-age-ms={model.ageMs === null ? "" : String(Math.round(model.ageMs))}
        data-stale={String(model.stale)}
      >
        <div className="diagnostics__header">
          <span className="drawer-dot" />
          <span className="diagnostics__title">DIAGNOSTICS</span>
          <button type="button" className="drawer-close" onClick={onClose} aria-label="Close diagnostics">
            ✕
          </button>
        </div>

        <div className="diagnostics__toggles" role="group" aria-label="Diagnostic layers">
          {TOGGLE_DEFS.map((definition) => (
            <button
              key={definition.key}
              type="button"
              className={`diagnostics-toggle ${toggles[definition.key] ? "diagnostics-toggle--on" : ""}`}
              aria-pressed={toggles[definition.key]}
              data-diagnostic-toggle={definition.key}
              title={definition.hint}
              onClick={() => onToggle(definition.key)}
            >
              {definition.label}
            </button>
          ))}
        </div>

        <dl className="diagnostics__rows">
          {model.rows.map((row) => (
            <div
              key={row.key}
              className={`diagnostics-row diagnostics-row--${row.tone}`}
              data-diagnostic-row={row.key}
              data-available={String(row.available)}
            >
              <dt>{row.label}</dt>
              <dd className="mono">{row.value}</dd>
            </div>
          ))}
          {model.rows.length === 0 && (
            <div className="diagnostics-row diagnostics-row--muted">
              <dt>LAYERS</dt>
              <dd className="mono">none enabled</dd>
            </div>
          )}
        </dl>
      </aside>
    </>
  );
}
