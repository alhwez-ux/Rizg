import { apiFetch } from "@/lib/api";

export type TasiCorrectionState = "safe" | "approach" | "confirmed" | "ending" | "rebound";

export type TasiCorrectionPayload = {
  success?: boolean;
  symbol?: string;
  state?: TasiCorrectionState | null;
  label?: string;
  alert?: boolean;
  value?: number | null;
  change_percent?: number | null;
  reasons?: string[];
};

const STATES = new Set<TasiCorrectionState>(["safe", "approach", "confirmed", "ending", "rebound"]);

export function parseTasiCorrection(payload: TasiCorrectionPayload | null | undefined): TasiCorrectionPayload | null {
  if (!payload || typeof payload !== "object") return null;
  const state = payload.state;
  if (state != null && !STATES.has(state)) return null;
  return {
    state: state ?? null,
    label: typeof payload.label === "string" ? payload.label : "",
    alert: payload.alert === true,
    reasons: Array.isArray(payload.reasons) ? payload.reasons.filter((item) => typeof item === "string") : [],
  };
}

export async function fetchTasiCorrection(): Promise<TasiCorrectionPayload | null> {
  const response = await apiFetch("/api/v1/correction-radar/index", { timeoutMs: 12_000 });
  if (!response.ok) return null;
  return parseTasiCorrection((await response.json()) as TasiCorrectionPayload);
}

export function correctionLamp(state: TasiCorrectionState | null | undefined): "danger" | "warn" | "calm" | "settle" | "off" {
  if (state === "confirmed") return "danger";
  if (state === "approach") return "warn";
  if (state === "safe" || state === "rebound") return "calm";
  if (state === "ending") return "settle";
  return "off";
}
