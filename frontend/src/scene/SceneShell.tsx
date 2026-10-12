import type { SnapshotState } from "../App";
import type { SatelliteState } from "../contract";

/**
 * Day 2 scene shell: displays the canonical snapshot received from the core.
 *
 * Nothing here computes orbital state. The table is the renderer's honest view
 * of the contract until the Three.js scene replaces it on Day 3; the rendered
 * objects built then will be derived from these same SatelliteState records.
 */
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
  return (
    <div className="scene-shell" data-testid="scene-shell">
      <div className="scene-shell__placeholder">
        <div className="scene-shell__title">Constellab Scene</div>
        <div className="scene-shell__subtitle">Orbital viewport — 3D rendering starts Day 3</div>
        {snapshot.kind === "loading" && <div className="scene-shell__note">waiting for snapshot…</div>}
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
              <table className="snapshot__table">
                <thead>
                  <tr>
                    <th>id</th>
                    <th>position ECI (km)</th>
                    <th>velocity ECI (km/s)</th>
                    <th>a / i</th>
                  </tr>
                </thead>
                <tbody>
                  {snapshot.snapshot.satellites.map((sat) => (
                    <SatelliteRow key={sat.id} sat={sat} />
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
