import { apiUrl } from "@/lib/api";

export interface ConnectionSnapshot {
  healthy: boolean;
  plan_active: boolean;
  plan_reason: string | null;
  clients: number;
  owner?: string;
  is_connected: boolean;
  unsupported?: boolean;
}

const DISCONNECTED: ConnectionSnapshot = {
  healthy: false,
  plan_active: false,
  plan_reason: null,
  clients: 0,
  is_connected: false,
};

export const OWNER_CLIENT_ID = "owner";

export function connectionClientId(): string {
  return OWNER_CLIENT_ID;
}

export async function fetchConnectionStatus(): Promise<ConnectionSnapshot> {
  try {
    const response = await fetch(apiUrl("/api/v1/connection"), { cache: "no-store" });
    if (response.status === 404) {
      return {
        healthy: true,
        plan_active: true,
        plan_reason: null,
        clients: 0,
        is_connected: true,
        unsupported: true,
      };
    }
    if (!response.ok) {
      return { ...DISCONNECTED, plan_reason: `HTTP ${response.status}` };
    }
    const payload = (await response.json()) as Partial<ConnectionSnapshot>;
    return {
      healthy: payload.healthy !== false,
      plan_active: payload.plan_active !== false,
      plan_reason: payload.plan_reason ?? null,
      clients: Number(payload.clients) || 0,
      is_connected: payload.is_connected === true,
    };
  } catch {
    return DISCONNECTED;
  }
}

export async function beatConnection(clientId: string): Promise<ConnectionSnapshot | null> {
  try {
    const response = await fetch(apiUrl("/api/v1/connection/heartbeat"), {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Rizg-Client": clientId },
      body: JSON.stringify({ client_id: clientId }),
      cache: "no-store",
    });
    if (response.status === 404) return null;
    if (!response.ok) return null;
    const payload = (await response.json()) as Partial<ConnectionSnapshot>;
    return {
      healthy: payload.healthy !== false,
      plan_active: payload.plan_active !== false,
      plan_reason: payload.plan_reason ?? null,
      clients: Number(payload.clients) || 0,
      is_connected: payload.is_connected === true,
    };
  } catch {
    return null;
  }
}

export function releaseConnection(clientId: string): void {
  const url = apiUrl("/api/v1/connection/release");
  const body = JSON.stringify({ client_id: clientId });
  try {
    void fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Rizg-Client": clientId },
      body,
      keepalive: true,
      cache: "no-store",
    });
  } catch {
    // The tab is going away; the heartbeat TTL stops the backend feeds.
  }
}
