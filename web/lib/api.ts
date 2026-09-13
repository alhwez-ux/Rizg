const LOCAL_API = "http://127.0.0.1:8000";
const PROD_API = "https://rizg-backend.onrender.com";

function configuredBackend(): string {
  const fromEnv = (
    process.env.NEXT_PUBLIC_API_URL ||
    process.env.API_PROXY_URL ||
    ""
  )
    .trim()
    .replace(/\/$/, "");
  if (fromEnv) return fromEnv;
  return process.env.NODE_ENV === "production" ? PROD_API : LOCAL_API;
}

export const API_BASE = configuredBackend();

export function apiUrl(path: string): string {
  const normalized = path.startsWith("/") ? path : `/${path}`;
  return `${API_BASE}${normalized}`;
}

export function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const headers: Record<string, string> = {
    Accept: "application/json",
  };
  if (init.body != null) {
    headers["Content-Type"] = "application/json";
  }
  const controller = init.signal ? null : new AbortController();
  const timer = controller ? setTimeout(() => controller.abort(), 18_000) : null;
  return fetch(apiUrl(path), {
    ...init,
    signal: init.signal ?? controller?.signal,
    cache: init.cache ?? "no-store",
    headers: {
      ...headers,
      ...(init.headers ?? {}),
    },
  }).finally(() => {
    if (timer) clearTimeout(timer);
  });
}

export function wsUrlFor(symbol: string): string {
  const ticker = symbol.trim() || "4030";
  const explicit = process.env.NEXT_PUBLIC_WS_URL?.replace(/\/$/, "");
  if (explicit) {
    const root = explicit.replace(/\/ws\/liquidity(?:\/.*)?$/, "");
    return `${root}/ws/liquidity/${ticker}`;
  }
  const httpBase = API_BASE;
  const protocol = httpBase.startsWith("https") ? "wss" : "ws";
  const host = httpBase.replace(/^https?:\/\//, "");
  return `${protocol}://${host}/ws/liquidity/${ticker}`;
}
