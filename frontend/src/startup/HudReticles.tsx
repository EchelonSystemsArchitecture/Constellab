
export function HudReticles() {
  return (
    <div className="hud-reticles" aria-hidden="true">
      {/* Top Left Bracket */}
      <svg className="hud-reticle hud-reticle--top-left" viewBox="0 0 28 28">
        <path d="M 28 2 L 2 2 L 2 28" fill="none" stroke="currentColor" strokeWidth="1.75" />
      </svg>

      {/* Top Right Bracket */}
      <svg className="hud-reticle hud-reticle--top-right" viewBox="0 0 28 28">
        <path d="M 0 2 L 26 2 L 26 28" fill="none" stroke="currentColor" strokeWidth="1.75" />
      </svg>

      {/* Bottom Left Bracket */}
      <svg className="hud-reticle hud-reticle--bottom-left" viewBox="0 0 28 28">
        <path d="M 2 0 L 2 26 L 28 26" fill="none" stroke="currentColor" strokeWidth="1.75" />
      </svg>

      {/* Bottom Right Bracket */}
      <svg className="hud-reticle hud-reticle--bottom-right" viewBox="0 0 28 28">
        <path d="M 26 0 L 26 26 L 0 26" fill="none" stroke="currentColor" strokeWidth="1.75" />
      </svg>
    </div>
  );
}
