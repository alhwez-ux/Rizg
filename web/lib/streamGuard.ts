const listeners = new Set<() => void>();
const intervals = new Set<number>();
const sockets = new Set<WebSocket>();
const inflight = new Set<AbortController>();

let installed = false;
let halted = false;
let armed = false;
let nativeSetInterval: typeof window.setInterval | null = null;
let nativeClearInterval: ((id: number) => void) | null = null;
let nativeFetch: typeof window.fetch | null = null;

function emit(): void {
  for (const listener of listeners) listener();
}

export function streamsHalted(): boolean {
  return halted;
}

export function streamsArmed(): boolean {
  return armed && !halted;
}

export function subscribeStreams(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function isDataRequest(input: string): boolean {
  const url = input.toLowerCase();
  if (url.includes("/api/auth/") || url.includes("/api/account/")) return false;
  return (
    url.includes("onrender.com") ||
    url.includes("/api/v1/") ||
    url.includes("/api/market") ||
    url.includes("/api/radar") ||
    url.includes("/api/opportunities") ||
    url.includes("/api/analysts") ||
    url.includes("/api/version") ||
    url.includes("version.json")
  );
}

function requestUrl(input: RequestInfo | URL): string {
  if (typeof input === "string") return input;
  if (input instanceof URL) return input.href;
  return input.url;
}

function closedSocket(url: string): WebSocket {
  return {
    url,
    readyState: 3,
    protocol: "",
    extensions: "",
    bufferedAmount: 0,
    binaryType: "blob",
    onopen: null,
    onmessage: null,
    onerror: null,
    onclose: null,
    close() {},
    send() {},
    addEventListener() {},
    removeEventListener() {},
    dispatchEvent() {
      return false;
    },
  } as unknown as WebSocket;
}

export function installStreamGuard(): void {
  if (installed || typeof window === "undefined") return;
  installed = true;
  nativeSetInterval = window.setInterval.bind(window);
  nativeClearInterval = window.clearInterval.bind(window) as (id: number) => void;
  nativeFetch = window.fetch.bind(window);
  const NativeWebSocket = window.WebSocket;

  window.setInterval = ((handler: TimerHandler, timeout?: number, ...args: unknown[]) => {
    if (halted || !nativeSetInterval) return 0;
    const id = Number(
      nativeSetInterval(
        () => {
          if (halted) return;
          if (typeof handler === "function") {
            handler(...(args as []));
          }
        },
        timeout,
      ),
    );
    intervals.add(id);
    return id;
  }) as typeof window.setInterval;

  window.clearInterval = ((id: number) => {
    intervals.delete(id);
    nativeClearInterval?.(id);
  }) as typeof window.clearInterval;

  window.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = requestUrl(input);
    if (!nativeFetch) return fetch(input, init);
    if (halted && isDataRequest(url)) {
      return new Response(JSON.stringify({ halted: true }), {
        status: 204,
        headers: { "content-type": "application/json", "cache-control": "no-store" },
      });
    }
    if (!isDataRequest(url)) return nativeFetch(input, init);

    const controller = new AbortController();
    const signal = init?.signal;
    if (signal) {
      if (signal.aborted) controller.abort();
      else signal.addEventListener("abort", () => controller.abort(), { once: true });
    }
    inflight.add(controller);
    try {
      const response = await nativeFetch(input, { ...init, signal: controller.signal });
      if (response.status === 401 && url.includes("/api/") && !url.includes("onrender.com")) {
        haltAllStreams();
        if (window.location.pathname !== "/login") window.location.replace("/login");
      }
      return response;
    } finally {
      inflight.delete(controller);
    }
  }) as typeof window.fetch;

  function TrackedWebSocket(url: string | URL, protocols?: string | string[]): WebSocket {
    if (halted) return closedSocket(String(url));
    const socket = protocols === undefined ? new NativeWebSocket(url) : new NativeWebSocket(url, protocols);
    sockets.add(socket);
    socket.addEventListener("close", () => sockets.delete(socket));
    return socket;
  }

  TrackedWebSocket.CONNECTING = NativeWebSocket.CONNECTING;
  TrackedWebSocket.OPEN = NativeWebSocket.OPEN;
  TrackedWebSocket.CLOSING = NativeWebSocket.CLOSING;
  TrackedWebSocket.CLOSED = NativeWebSocket.CLOSED;
  TrackedWebSocket.prototype = NativeWebSocket.prototype;
  window.WebSocket = TrackedWebSocket as unknown as typeof WebSocket;
}

export function prepareStreams(enabled: boolean): void {
  halted = !enabled;
  armed = enabled;
}

export function armStreams(): void {
  const changed = !armed || halted;
  prepareStreams(true);
  if (changed) emit();
}

export function haltAllStreams(): void {
  halted = true;
  armed = false;
  for (const id of intervals) nativeClearInterval?.(id);
  intervals.clear();
  for (const controller of inflight) controller.abort();
  inflight.clear();
  for (const socket of sockets) {
    try {
      socket.close();
    } catch {
      /* already closed */
    }
  }
  sockets.clear();
  emit();
}
