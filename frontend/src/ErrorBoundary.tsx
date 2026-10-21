import { Component, type ErrorInfo, type ReactNode } from "react";

interface ErrorBoundaryProps {
  children: ReactNode;
}

interface ErrorBoundaryState {
  message: string | null;
}

/**
 * Day 12: a renderer crash must not leave a blank window. The boundary shows the
 * failure and lets the user rebuild the viewport; simulation state stays owned by
 * the core, so a rebuild only re-subscribes to the state stream.
 */
export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { message: null };

  static getDerivedStateFromError(error: unknown): ErrorBoundaryState {
    return { message: error instanceof Error ? error.message : String(error) };
  }

  componentDidCatch(error: unknown, info: ErrorInfo) {
    // Kept visible in devtools; no simulation state is touched by the failure.
    console.error("viewport failed to render", error, info.componentStack);
  }

  private readonly retry = () => this.setState({ message: null });

  render() {
    if (this.state.message !== null) {
      return (
        <div className="scene-shell__unavailable" role="alert" data-testid="scene-error-boundary">
          <h2>Viewport Failed</h2>
          <p>The renderer stopped unexpectedly. The simulation core is unaffected.</p>
          <p className="mono">{this.state.message}</p>
          <button type="button" className="tool-btn" onClick={this.retry}>
            REBUILD VIEWPORT
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
