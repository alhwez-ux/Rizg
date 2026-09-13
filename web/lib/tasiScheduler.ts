import { apiFetch } from "@/lib/api";

export interface SchedulerStatus {
  success: boolean;
  enabled: boolean;
  running: boolean;
  timezone: string;
  clock: string;
  phase: string;
  phase_label: string;
  intraday: boolean;
  jobs: { id: string; next_run_at: string | null }[];
  last: {
    open?: { ran_at?: string; symbols?: number } | null;
    scan?: { ran_at?: string; scanned?: number; alerts?: number } | null;
    close?: { ran_at?: string; ranking_updated?: number; recommendations?: number } | null;
  };
}

export async function fetchSchedulerStatus(): Promise<SchedulerStatus | null> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), 4000);
  try {
    const response = await apiFetch("/api/v1/market/scheduler", { signal: controller.signal });
    if (!response.ok) return null;
    return (await response.json()) as SchedulerStatus;
  } catch {
    return null;
  } finally {
    window.clearTimeout(timer);
  }
}
