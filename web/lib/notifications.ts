import { apiFetch } from "@/lib/api";

export type AlertKind = "trap" | "inflow" | "opportunity";
export type NoticeType = "success" | "alert" | "info";

export interface MarketAlert {
  id: string;
  kind: AlertKind;
  type: NoticeType;
  symbol: string;
  name: string;
  title: string;
  message: string;
  at: string;
  time: string;
}

const KIND_ORDER: Record<AlertKind, number> = { trap: 0, inflow: 1, opportunity: 2 };

function noticeType(kind: AlertKind): NoticeType {
  if (kind === "inflow") return "success";
  if (kind === "trap") return "alert";
  return "info";
}

function noticeTime(at: string): string {
  const stamp = at.slice(0, 10);
  const [year, month, day] = stamp.split("-");
  if (!year || !month || !day) return "قبل قليل";
  return `${day}/${month}/${year}`;
}

function alertBase(
  id: string,
  kind: AlertKind,
  symbol: string,
  name: string,
  title: string,
  message: string,
  at: string,
): MarketAlert {
  return { id, kind, type: noticeType(kind), symbol, name, title, message, at, time: noticeTime(at) };
}

export function collectMarketAlerts(): MarketAlert[] {
  return [];
}

export async function collectLiveAlerts(): Promise<MarketAlert[]> {
  const response = await apiFetch("/api/v1/tickchart/alerts");
  const payload = (await response.json().catch(() => null)) as {
    data?: Array<{
      id?: string;
      kind?: string;
      symbol?: string;
      name?: string;
      title?: string;
      message?: string;
    }>;
  } | null;
  if (!response.ok || !payload) return [];
  const now = new Date().toISOString();
  const alerts: MarketAlert[] = [];
  for (const row of payload.data ?? []) {
    const kind = row.kind === "trap" || row.kind === "inflow" || row.kind === "opportunity" ? row.kind : "opportunity";
    alerts.push(
      alertBase(
        String(row.id || `${kind}-${row.symbol}`),
        kind,
        String(row.symbol || ""),
        String(row.name || row.symbol || ""),
        String(row.title || ""),
        String(row.message || ""),
        now,
      ),
    );
  }
  alerts.sort((left, right) => KIND_ORDER[left.kind] - KIND_ORDER[right.kind] || left.symbol.localeCompare(right.symbol));
  return alerts;
}
