export interface ViewportHost {
  readonly clientWidth: number;
  readonly clientHeight: number;
}

export interface ViewportRuntime {
  requestFrame(callback: () => void): number;
  cancelFrame(id: number): void;
  observeResize(host: ViewportHost, callback: () => void): () => void;
  pixelRatio(): number;
}

export interface ViewportCallbacks {
  resize(width: number, height: number, pixelRatio: number): void;
  /**
   * Called once per rendered frame. When `dt` is supplied it is the elapsed real
   * seconds since the previous frame; callers should use it for time-based motion
   * (e.g. Earth rotation) so frame-rate changes do not change the visual speed.
   */
  render(dt?: number): void;
  dispose(): void;
}

export function startViewport(
  host: ViewportHost,
  callbacks: ViewportCallbacks,
  runtime: ViewportRuntime,
  maxPixelRatio: number,
): () => void {
  let disposed = false;
  let frame: number;
  let lastTs = 0;
  const resize = () => {
    if (disposed) return;
    callbacks.resize(
      Math.max(1, host.clientWidth),
      Math.max(1, host.clientHeight),
      Math.min(maxPixelRatio, Math.max(1, runtime.pixelRatio())),
    );
  };
  const draw = (dt?: number) => {
    if (disposed) return;
    if (dt !== undefined) callbacks.render(dt);
    else callbacks.render();
    frame = runtime.requestFrame(() => draw(elapsed()));
  };
  const elapsed = (): number => {
    const now = performance.now();
    const dt = Math.min(0.1, (now - lastTs) / 1000);
    lastTs = now;
    return dt;
  };
  resize();
  lastTs = performance.now();
  const stopObserving = runtime.observeResize(host, resize);
  frame = runtime.requestFrame(() => draw(elapsed()));

  return () => {
    if (disposed) return;
    disposed = true;
    runtime.cancelFrame(frame);
    frame = 0;
    stopObserving();
    callbacks.dispose();
  };
}


export const BROWSER_RUNTIME: ViewportRuntime = {
  requestFrame: (callback) => requestAnimationFrame(callback),
  cancelFrame: (id) => cancelAnimationFrame(id),
  observeResize: (host, callback) => {
    const observer = new ResizeObserver(callback);
    observer.observe(host as HTMLElement);
    window.addEventListener("resize", callback);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", callback);
    };
  },
  pixelRatio: () => window.devicePixelRatio,
};
