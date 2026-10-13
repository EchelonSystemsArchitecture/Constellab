import { useEffect, useRef, useState } from "react";
import type { SnapshotState } from "../App";
import type { SatelliteState } from "../contract";
import { EarthScene } from "./EarthScene";

const km = (v: number) => v.toFixed(1);
const kms = (v: number) => v.toFixed(3);

function SatelliteRow({ sat }: { sat: SatelliteState }) {
  const [x, y, z] = sat.position_eci_km;
  const [vx, vy, vz] = sat.velocity_eci_km_s;
  return (
    <tr data-satellite-id={sat.id}>
      <td className="mono">{sat.id}</td>
      <td className="mono">{`${km(x)}, ${km(y)}, ${km(z)}`}</td>
      <td className="mono">{`${kms(vx)}, ${kms(vy)}, ${kms(vz)}`}</td>
      <td className="mono">{sat.orbit ? `${km(sat.orbit.semi_major_axis_km)} km / ${sat.orbit.inclination_deg}°` : "—"}</td>
    </tr>
  );
}

export function SceneShell({ snapshot }: { snapshot: SnapshotState }) {
  const viewport = useRef<HTMLDivElement>(null);
  const scene = useRef<EarthScene | null>(null);
  const [sceneError, setSceneError] = useState<string | null>(null);

  useEffect(() => {
    if (!viewport.current) return;
    try {
      scene.current = new EarthScene(viewport.current);
      setSceneError(null);
    } catch (err) {
      setSceneError(err instanceof Error ? err.message : String(err));
    }
    return () => {
      scene.current?.dispose();
      scene.current = null;
    };
  }, []);

  useEffect(() => {
    scene.current?.setSnapshot(snapshot.kind === "ready" ? snapshot.snapshot : null);
  }, [snapshot]);

  return (
    <section className="scene-shell" data-testid="scene-shell" aria-label="Orbital viewport">
      <div className="scene-shell__viewport" ref={viewport} data-testid="earth-viewport" />
      <div className="scene-shell__toolbar">
        <div>
          <div className="scene-shell__title">Earth / Orbital Viewport</div>
          <div className="scene-shell__subtitle">Offline schematic texture · fixed Earth · ECI reference</div>
        </div>
        <div className="scene-shell__controls" role="group" aria-label="Camera controls">
          <button disabled={!!sceneError} onClick={() => scene.current?.zoom("in")} aria-label="Zoom in">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M7 1v12M1 7h12" />
            </svg>
          </button>
          <button disabled={!!sceneError} onClick={() => scene.current?.zoom("out")} aria-label="Zoom out">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M1 7h12" />
            </svg>
          </button>
          <button disabled={!!sceneError} onClick={() => scene.current?.reset()}>
            Reset view
          </button>
        </div>
      </div>
      {sceneError && (
        <div className="scene-shell__unavailable" role="alert">
          <h2>3D viewport unavailable</h2>
          <p>WebGL is required. Enable hardware acceleration or use a WebGL-capable device.</p>
          <p className="mono">{sceneError}</p>
        </div>
      )}
      <div className="scene-shell__telemetry">
        <div className="scene-shell__hint">Drag to orbit · scroll / pinch to zoom · satellites &amp; paths arrive Day 4</div>
        {snapshot.kind === "loading" && (
          <div className="scene-shell__note">
            <span className="loading-screen__spinner" style={{ display: "inline-block", verticalAlign: "middle", marginRight: 8 }} />
            waiting for snapshot…
          </div>
        )}
        {snapshot.kind === "rejected" && (
          <div className="scene-shell__error" data-testid="snapshot-error">
            <div>{snapshot.reason}</div>
            <ul>
              {snapshot.errors.map((e) => (
                <li key={e.path} className="mono">{`${e.path}: ${e.message}`}</li>
              ))}
            </ul>
          </div>
        )}
        {snapshot.kind === "ready" && (
          <div className="snapshot" data-testid="snapshot-view">
            <div className="snapshot__clock mono">
              {`scenario ${snapshot.snapshot.scenario_id} · epoch ${snapshot.snapshot.clock.epoch_utc} · t = ${snapshot.snapshot.clock.simulation_time_s.toFixed(1)} s · ×${snapshot.snapshot.clock.time_scale} · ${snapshot.snapshot.clock.paused ? "paused" : "running"} · ${snapshot.snapshot.satellites.length} satellites`}
            </div>
            {snapshot.snapshot.satellites.length > 0 && (
              <details className="snapshot__details">
                <summary>Core state / {snapshot.snapshot.satellites.length} satellites (not yet rendered)</summary>
                <div className="snapshot__scroll">
                  <table className="snapshot__table">
                    <thead>
                      <tr>
                        <th>ID</th>
                        <th>Position ECI (km)</th>
                        <th>Velocity ECI (km/s)</th>
                        <th>a / i</th>
                      </tr>
                    </thead>
                    <tbody>
                      {snapshot.snapshot.satellites.map((sat) => (
                        <SatelliteRow key={sat.id} sat={sat} />
                      ))}
                    </tbody>
                  </table>
                </div>
              </details>
            )}
          </div>
        )}
      </div>
    </section>
  );
}
