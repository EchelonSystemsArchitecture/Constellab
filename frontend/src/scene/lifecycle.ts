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
  render(): void;
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
  const resize = () => {
    if (disposed) return;
    callbacks.resize(
      Math.max(1, host.clientWidth),
      Math.max(1, host.clientHeight),
      Math.min(maxPixelRatio, Math.max(1, runtime.pixelRatio())),
    );
  };
  const draw = () => {
    if (disposed) return;
    callbacks.render();
    frame = runtime.requestFrame(draw);
  };
  resize();
  const stopObserving = runtime.observeResize(host, resize);
  frame = runtime.requestFrame(draw);

  return () => {
    if (disposed) return;
    disposed = true;
    runtime.cancelFrame(frame);
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
