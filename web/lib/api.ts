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

export const DEFAULT_API_TIMEOUT_MS = 18_000;
export const HEAVY_API_TIMEOUT_MS = 120_000;

export type ApiFetchInit = RequestInit & {
  /** Pass `null` to wait until the server responds. */
  timeoutMs?: number | null;
};

export class ApiTimeoutError extends Error {
  constructor(message = "انتهت مهلة الطلب") {
    super(message);
    this.name = "TimeoutError";
  }
}

export function apiUrl(path: string): string {
  const normalized = path.startsWith("/") ? path : `/${path}`;
  return `${API_BASE}${normalized}`;
}

function isAbortError(error: unknown): boolean {
  return (
    (error instanceof DOMException && error.name === "AbortError") ||
    (error instanceof Error && (error.name === "AbortError" || error.name === "TimeoutError"))
  );
}

export async function apiFetch(path: string, init: ApiFetchInit = {}): Promise<Response> {
  const { timeoutMs, signal, ...rest } = init;
  const headers: Record<string, string> = {
    Accept: "application/json",
  };
  if (rest.body != null) {
    headers["Content-Type"] = "application/json";
  }
  const timeout = signal ? null : timeoutMs === null ? null : timeoutMs ?? DEFAULT_API_TIMEOUT_MS;
  const controller = timeout != null && timeout > 0 ? new AbortController() : null;
  const timer = controller ? setTimeout(() => controller.abort(), timeout) : null;
  try {
    return await fetch(apiUrl(path), {
      ...rest,
      signal: signal ?? controller?.signal,
      cache: rest.cache ?? "no-store",
      headers: {
        ...headers,
        ...(rest.headers ?? {}),
      },
    });
  } catch (error) {
    if (controller?.signal.aborted || isAbortError(error)) {
      throw new ApiTimeoutError();
    }
    throw error;
  } finally {
    if (timer) clearTimeout(timer);
  }
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
