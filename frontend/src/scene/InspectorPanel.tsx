import type { SatelliteState, SimulationSnapshot } from "../contract";
import { getSatelliteColor, BRAND_COLORS } from "./orbit";
import { resolveSelection, satelliteInspectorSections, simulationUtc } from "./selection";

interface InspectorPanelProps {
  snapshot: SimulationSnapshot | null;
  satellites: SatelliteState[];
  selectedSatId: string | null;
  onSelect: (id: string) => void;
  onFocus: (id: string) => void;
  onClearSelection: () => void;
  onClose: () => void;
  /** True when a focus request has no live 3D marker (2D view or stale id). */
  focusAvailable: boolean;
}

const hex = (color: number) => `#${color.toString(16).padStart(6, "0")}`;

function indexOfSelected(satellites: SatelliteState[], id: string | null): number {
  return id ? satellites.findIndex((s) => s.id === id) : -1;
}

/**
 * Day 7 inspector: identity, orbit elements, ECI state and time base for the
 * selected satellite. Every value comes from the snapshot; absent fields show
 * UNAVAILABLE instead of a fabricated zero.
 */
export function InspectorPanel({
  snapshot,
  satellites,
  selectedSatId,
  onSelect,
  onFocus,
  onClearSelection,
  onClose,
  focusAvailable,
}: InspectorPanelProps) {
  const selection = resolveSelection(selectedSatId, satellites);
  const selectedIndex = indexOfSelected(satellites, selectedSatId);
  const color = selectedIndex >= 0 ? getSatelliteColor(selectedIndex) : BRAND_COLORS.coreBlue;
  const sections =
    selection.kind === "selected"
      ? satelliteInspectorSections(selection.satellite, snapshot?.clock, snapshot)
      : [];

  return (
    <aside className="inspector" data-testid="satellite-inspector" aria-label="Satellite Inspector">
      <div className="inspector__header">
        <div className="inspector__title">
          <span className="drawer-dot" />
          <span>SATELLITE INSPECTOR</span>
        </div>
        <div className="inspector__header-actions">
          <button
            type="button"
            className="inspector__icon-btn"
            onClick={onClose}
            aria-label="Close inspector"
            title="Close inspector"
          >
            ✕
          </button>
        </div>
      </div>

      {/* Selection: chips for small fleets, a typed select once badges would wrap */}
      <div className="inspector__chips" role="tablist" aria-label="Select satellite">
        {satellites.length === 0 && <span className="inspector__empty-note">NO SATELLITES IN SNAPSHOT</span>}
        {satellites.length > 8 && (
          <select
            className="inspector__select mono"
            aria-label="Select satellite by id"
            value={selectedSatId ?? ""}
            onChange={(event) => {
              if (event.target.value) onSelect(event.target.value);
            }}
          >
            <option value="">SELECT SATELLITE…</option>
            {satellites.map((sat) => (
              <option key={sat.id} value={sat.id}>{sat.id}</option>
            ))}
          </select>
        )}
        {satellites.length <= 8 && satellites.map((sat, i) => {
          const chipColor = hex(getSatelliteColor(i));
          const active = sat.id === selectedSatId;
          return (
            <button
              key={sat.id}
              type="button"
              role="tab"
              aria-selected={active}
              data-satellite-id={sat.id}
              className={`inspector__chip ${active ? "inspector__chip--active" : ""}`}
              style={active ? { borderColor: chipColor, color: chipColor } : undefined}
              onClick={() => onSelect(sat.id)}
            >
              <span className="tactical-status-dot" style={{ backgroundColor: chipColor }} />
              {i + 1}. {sat.id}
            </button>
          );
        })}
        {satellites.length > 8 && (
          <span className="inspector__empty-note">{`${satellites.length} ENTITIES — USE THE SELECTOR`}</span>
        )}
      </div>

      {selection.kind === "none" && (
        <div className="inspector__body inspector__body--muted">
          No satellite selected. Click a marker in the viewport, or pick an entity above.
        </div>
      )}

      {selection.kind === "missing" && (
        <div className="inspector__body inspector__body--missing" role="alert">
          <div className="inspector__missing-title">SELECTION NOT IN SNAPSHOT</div>
          <div className="mono">{selection.id}</div>
          <p>
            This id was selected earlier but the current snapshot does not carry it. Its previous
            values are intentionally not shown.
          </p>
          <button type="button" className="inspector__link-btn" onClick={onClearSelection}>
            CLEAR SELECTION
          </button>
        </div>
      )}

      {selection.kind === "selected" && (
        <div className="inspector__body">
          <div className="inspector__hero" style={{ borderColor: hex(color) }}>
            <div className="inspector__hero-main">
              <span className="inspector__hero-id mono">{selection.satellite.id}</span>
              <span className="inspector__hero-swatch" style={{ backgroundColor: hex(color) }} />
            </div>
            <div className="inspector__hero-actions">
              <button
                type="button"
                className="inspector__action-btn"
                onClick={() => onFocus(selection.satellite.id)}
                disabled={!focusAvailable}
                title={focusAvailable ? "Aim the camera at this satellite" : "Focus needs the 3D viewport"}
              >
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="12" cy="12" r="4" />
                  <path d="M12 2v4M12 18v4M2 12h4M18 12h4" />
                </svg>
                FOCUS
              </button>
              <button type="button" className="inspector__action-btn" onClick={onClearSelection}>
                CLEAR
              </button>
            </div>
            <div className="inspector__hero-clock mono">
              {`t+${(snapshot?.clock.simulation_time_s ?? 0).toFixed(1)}s · ${simulationUtc(snapshot?.clock)}`}
            </div>
          </div>

          <div className="inspector__scroll">
            {sections.map((section) => (
              <section className="inspector__section" key={section.id}>
                <h3 className="inspector__section-title">{section.title}</h3>
                <dl className="inspector__grid">
                  {section.rows.map((r) => (
                    <div className="inspector__row" key={r.key} data-field={r.key}>
                      <dt className="inspector__label">{r.label}</dt>
                      <dd
                        className={`inspector__value mono ${r.available ? "" : "inspector__value--unavailable"}`}
                      >
                        {r.value}
                        {r.unit && r.available ? <span className="inspector__unit">{r.unit}</span> : null}
                      </dd>
                    </div>
                  ))}
                </dl>
              </section>
            ))}

            {snapshot === null && (
              <div className="inspector__body--muted">
                Snapshot unavailable — identity can be shown, simulation fields can not.
              </div>
            )}
          </div>
        </div>
      )}
    </aside>
  );
}
