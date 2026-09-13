import { apiFetch } from "@/lib/api";

export interface TickChartStatus {
  enabled: boolean;
  connected: boolean;
  trades_live: boolean;
  depth_live: boolean;
  autosync_enabled: boolean;
  autosync_watching: boolean;
  autosync_files: number;
  last_file: string | null;
  last_ingested: number;
  last_sync_at: string | null;
  source: string;
}

export async function fetchTickChartStatus(): Promise<TickChartStatus | null> {
  try {
    const response = await apiFetch("/api/v1/tickchart/status");
    const payload = (await response.json().catch(() => null)) as TickChartStatus | null;
    if (!response.ok || !payload) return null;
    return payload;
  } catch {
    return null;
  }
}
