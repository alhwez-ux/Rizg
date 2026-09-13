import { TASI_MARKET, MARKET_AS_OF, valueTraded } from "@/lib/marketData";
import { radarFromMarket, recommendationsFromMarket } from "@/lib/marketEngine";
import { fetchSchedulerStatus } from "@/lib/tasiScheduler";

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
  const [year, month, day] = at.slice(0, 10).split("-");
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
  at = MARKET_AS_OF,
): MarketAlert {
  return { id, kind, type: noticeType(kind), symbol, name, title, message, at, time: noticeTime(at) };
}

export function collectMarketAlerts(): MarketAlert[] {
  const alerts: MarketAlert[] = [];
  for (const company of TASI_MARKET) {
    const radar = radarFromMarket(company.symbol);
    const report = radar?.analysis;
    if (!report) continue;
    const volume = Math.round(company.volume).toLocaleString("en-US");
    const value = (valueTraded(company) / 1_000_000).toFixed(1);
    if (report.exit || (report.trap && company.change_percent < 0)) {
      alerts.push(
        alertBase(
          `trap-${company.symbol}`,
          "trap",
          company.symbol,
          company.name,
          "فخ هبوط محتمل (Bear Trap)",
          `${company.name} (${company.symbol}) يتراجع ${company.change_percent}% مع حجم ${volume} وقيمة ${value} مليون ر.س.`,
        ),
      );
      continue;
    }
    if (report.entry || (report.net_flow > 0 && company.change_percent >= 0.35)) {
      alerts.push(
        alertBase(
          `inflow-${company.symbol}`,
          "inflow",
          company.symbol,
          company.name,
          "تدفق سيولة مؤسسي",
          `رصد حجم تداول عالي ودخول سيولة إيجابية على ${company.name} (${company.symbol}) مع تغير +${company.change_percent}%.`,
        ),
      );
    }
  }
  for (const row of recommendationsFromMarket().data) {
    if (alerts.some((item) => item.symbol === row.symbol)) continue;
    alerts.push(
      alertBase(
        `opp-${row.symbol}-${row.signal_kind}`,
        "opportunity",
        row.symbol,
        row.name,
        row.signal_type,
        row.reason,
      ),
    );
  }
  alerts.sort((left, right) => KIND_ORDER[left.kind] - KIND_ORDER[right.kind] || left.symbol.localeCompare(right.symbol));
  return alerts;
}

export async function collectLiveAlerts(): Promise<MarketAlert[]> {
  const base = collectMarketAlerts();
  const scheduler = await fetchSchedulerStatus();
  const scan = scheduler?.last?.scan;
  if (!scan?.alerts) return base;
  const extra = alertBase(
    `scan-${scan.ran_at ?? "live"}`,
    "opportunity",
    "TASI",
    "تاسي",
    "تحديث مصفوفة التصنيف",
    `المجدول رصد ${scan.alerts} إشارة خلال مسح ${scan.scanned ?? 0} رمزاً.`,
    scan.ran_at ?? MARKET_AS_OF,
  );
  if (base.some((item) => item.id === extra.id)) return base;
  return [extra, ...base];
}
