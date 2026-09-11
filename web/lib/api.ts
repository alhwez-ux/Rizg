export const API_BASE = (
  process.env.NEXT_PUBLIC_API_URL ??
  (process.env.NODE_ENV === "production" ? "" : "http://localhost:8000")
).replace(/\/$/, "");

export function apiUrl(path: string): string {
  const normalized = path.startsWith("/") ? path : `/${path}`;
  return `${API_BASE}${normalized}`;
}

export function wsUrlFor(symbol: string): string {
  const ticker = symbol.trim() || "4030";
  const explicit = process.env.NEXT_PUBLIC_WS_URL?.replace(/\/$/, "");
  if (explicit) {
    const root = explicit.replace(/\/ws\/liquidity(?:\/.*)?$/, "");
    return `${root}/ws/liquidity/${ticker}`;
  }
  const httpBase = API_BASE || (typeof window !== "undefined" ? window.location.origin : "http://localhost:8000");
  const protocol = httpBase.startsWith("https") ? "wss" : "ws";
  const host = httpBase.replace(/^https?:\/\//, "");
  return `${protocol}://${host}/ws/liquidity/${ticker}`;
}
