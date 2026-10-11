/**
 * Day 1 scene shell: an empty, honest placeholder.
 *
 * The real Three.js scene (Earth, satellites, orbit paths) is built from
 * Day 3 onward. This shell reserves the scene viewport and renders no
 * simulated state, so later days render into the real application instead
 * of a throwaway prototype.
 */
export function SceneShell() {
  return (
    <div className="scene-shell" data-testid="scene-shell">
      <div className="scene-shell__placeholder">
        <div className="scene-shell__title">Constellab Scene</div>
        <div className="scene-shell__subtitle">
          Orbital viewport — rendering starts Day 3
        </div>
      </div>
    </div>
  );
}
