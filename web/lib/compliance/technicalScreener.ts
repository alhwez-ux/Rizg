import type { RadarTableRow } from "@/lib/firebase/types";
import type { ScreenerRow } from "@/lib/screener";

export type OpportunityKind = "BREAKOUT" | "BOUNCE" | "MOMENTUM" | "OVERSOLD";

export interface MarketOpportunity {
  symbol: string;
  companyNameAr: string;
  companyNameEn: string;
  currentStatus: "PURE" | "MIXED";
  financialGrade: RadarTableRow["financialGrade"];
  kind: OpportunityKind;
  score: number;
  reasons: string[];
  rsi: number | null;
  ema50: number | null;
  ema200: number | null;
  macd: number | null;
  volumeRatio: number | null;
}

function clamp(value: number, min = 0, max = 100): number {
  if (!Number.isFinite(value)) return min;
  return Math.min(max, Math.max(min, value));
}

function volumeRatio(row: RadarTableRow, live: ScreenerRow | undefined): number {
  if (live?.volume_surge != null && live.volume_surge > 0) return live.volume_surge;
  if (live && row.avgVolume && row.avgVolume > 0) return live.volume / row.avgVolume;
  return 1;
}

/**
 * Rank PURE/MIXED names for day-trade tape. Live net-flow and buy pressure
 * decide the opportunity — RSI/EMA/MACD only nudge the score, they never block.
 */
export function scanMarketOpportunities(
  stocks: RadarTableRow[],
  liveRows: ScreenerRow[] = [],
): MarketOpportunity[] {
  const liveBySymbol = new Map(liveRows.map((row) => [row.symbol, row]));

  return stocks
    .filter((row) => row.currentStatus === "PURE" || row.currentStatus === "MIXED")
    .flatMap((row) => {
      const live = liveBySymbol.get(row.symbol);
      const rsi = row.rsi;
      const ema50 = row.ema50;
      const ema200 = row.ema200;
      const macd = row.macd;
      const ratio = volumeRatio(row, live);
      const change = live?.change_percent ?? 0;
      const netFlow = live?.net_flow ?? 0;
      const buyRatio = live?.buy_ratio;
      const reasons: string[] = [];
      let kind: OpportunityKind = "MOMENTUM";
      let score = 28;

      if (live?.entry_signal || (netFlow > 0 && (buyRatio == null || buyRatio >= 0.51))) {
        kind = netFlow > 0 && change < 0 ? "BOUNCE" : "MOMENTUM";
        score = 72 + Math.min(18, Math.abs(netFlow) / 20_000) + (ratio > 1.2 ? 6 : 0);
        reasons.push("دخول: صافي تدفق موجب مع ضغط شراء نشط");
      } else if (live?.exit_signal || netFlow < 0) {
        kind = "OVERSOLD";
        score = 40 + Math.min(12, Math.abs(netFlow) / 25_000);
        reasons.push("خروج: صافي التدفق محايد أو سالب — قفل المكاسب");
      } else if (netFlow > 0) {
        kind = "BOUNCE";
        score = 58 + Math.min(12, netFlow / 15_000);
        reasons.push("زخم سيولة داخل بدون شرط متوسطات");
      } else if (rsi != null && ema50 != null && ema200 != null && macd != null) {
        if (rsi < 32 && (change > 0 || netFlow > 0)) {
          kind = "OVERSOLD";
          score = 50 + (32 - rsi) * 0.8;
          reasons.push("تشبع بيعي اختياري — لا يمنع الإشارة الحية");
        } else if (ema50 > ema200 && macd > 0) {
          kind = "MOMENTUM";
          score = 42 + Math.min(12, macd * 20);
          reasons.push("زخم فني مساعد فقط");
        } else {
          return [];
        }
      } else {
        return [];
      }

      if (live?.entry_signal) {
        score += 10;
        reasons.push("إشارة سيولة دخول موثّقة على الشريط");
      }
      if (ratio >= 1.8) reasons.push("حجم التداول أعلى بوضوح من متوسطه");

      return [
        {
          symbol: row.symbol,
          companyNameAr: row.companyNameAr,
          companyNameEn: row.companyNameEn,
          currentStatus: row.currentStatus,
          financialGrade: row.financialGrade,
          kind,
          score: Math.round(clamp(score)),
          reasons,
          rsi,
          ema50,
          ema200,
          macd,
          volumeRatio: Number(ratio.toFixed(2)),
        },
      ];
    })
    .sort((a, b) => b.score - a.score || a.symbol.localeCompare(b.symbol, "en"));
}
