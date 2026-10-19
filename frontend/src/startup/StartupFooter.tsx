
export function StartupFooter() {
  return (
    <footer className="startup-footer" role="contentinfo">
      {/* Bottom Left Motto HUD */}
      <div className="startup-footer__motto">
        <span className="startup-motto-row startup-motto-row--small">SMALL</span>
        <span className="startup-motto-row startup-motto-row--anomalies">ANOMALIES</span>
        <span className="startup-motto-row startup-motto-row--big">BIG</span>
        <div className="startup-motto-row startup-motto-row--questions">
          <span>QUESTIONS</span>
          <div className="startup-motto-underline" aria-hidden="true" />
        </div>
      </div>

      {/* Bottom Right System Badge */}
      <div className="startup-footer__status">
        <div className="startup-footer__status-main">
          <span className="startup-footer__status-dot" aria-hidden="true" />
          <span className="startup-footer__status-brand">constellab</span>
        </div>
        <div className="startup-footer__status-version">V1.0 ONLINE</div>
      </div>
    </footer>
  );
}
