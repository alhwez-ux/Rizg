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
 * Rank PURE/MIXED names only. PROHIBITED rows never reach this function.
 * Mixes seeded RSI/EMA/MACD with live tape flow and volume when available.
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
      if (rsi == null || ema50 == null || ema200 == null || macd == null) return [];

      const ratio = volumeRatio(row, live);
      const change = live?.change_percent ?? 0;
      const netFlow = live?.net_flow ?? 0;
      const goldenCross = ema50 > ema200;
      const reasons: string[] = [];
      let kind: OpportunityKind = "MOMENTUM";
      let score = 35;

      if (rsi < 32 && (change > 0 || netFlow > 0)) {
        kind = "OVERSOLD";
        score = 58 + (32 - rsi) * 1.1 + (netFlow > 0 ? 8 : 0);
        reasons.push("تشبع بيعي على RSI مع انعكاس إيجابي");
      } else if (goldenCross && ratio >= 1.45 && change > 0.8) {
        kind = "BREAKOUT";
        score = 70 + Math.min(18, (ratio - 1.4) * 12) + Math.min(8, change);
        reasons.push("اختراق مقاومة / تقاطع EMA 50 فوق 200 بحجم مرتفع");
      } else if (rsi < 42 && netFlow > 0 && Math.abs(ema50 - ema200) / ema200 < 0.04) {
        kind = "BOUNCE";
        score = 62 + (42 - rsi) * 0.7 + (ratio > 1.2 ? 6 : 0);
        reasons.push("ارتداد من دعم قريب من متوسط 200 مع تدفق داخل");
      } else if (goldenCross && macd > 0) {
        kind = "MOMENTUM";
        score = 55 + Math.min(20, macd * 40) + (netFlow > 0 ? 8 : 0);
        reasons.push("زخم صاعد: تقاطع متوسطات إيجابي وMACD فوق الصفر");
      } else {
        score = 28 + (goldenCross ? 8 : 0) + (macd > 0 ? 6 : 0);
        reasons.push("إشارة فنية ضعيفة أو محايدة");
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
