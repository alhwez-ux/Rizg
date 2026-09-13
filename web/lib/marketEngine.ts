import {
  MARKET_SOURCE,
  TASI_MARKET,
  companyBySymbol,
  netFlow,
  sessionBuyRatio,
  typicalPrice,
  valueTraded,
  type TasiCompany,
} from "@/lib/marketData";
import type { RankingRow, RankingMatrixResponse } from "@/lib/rankingMatrix";
import type { MarketRecommendation, RecommendationsResponse } from "@/lib/recommendations";
import type { LiveRadarResponse } from "@/lib/liveRadar";
import type {
  SectorCompany,
  SectorCompaniesResponse,
  SectorData,
  SectorRotationResponse,
} from "@/lib/sectorRotation";

const GROWTH_WEIGHT = 0.3;
const DIVIDEND_WEIGHT = 0.3;
const SOLVENCY_WEIGHT = 0.25;
const PE_WEIGHT = 0.15;

const CATEGORY_FORTRESS = "قلاع النمو والعوائد المتينة 🏰";
const CATEGORY_PROMISING = "شركات تشغيلية واعدة ومستقرة 📈";
const CATEGORY_AVERAGE = "شركات ذات أداء متوسط أو متحفظ ⚖️";
const CATEGORY_WEAK = "شركات ضعيفة النمو ⚠️لتجنبها";
const CATEGORY_LOSER = "الشركات الخاسرة وعالية المخاطر 🔴";

const STATUS_LEADER = "تدفق سيولة قوي (قائد السوق) 🚀";
const STATUS_ACCUMULATION = "مرحلة تجميع وهدوء إيجابي 📈";
const STATUS_OUTFLOW = "خروج سيولة / ضغط بيعي ⚠️";

function clipNorm(value: number, low: number, high: number, invert = false): number {
  const span = high - low;
  if (span <= 0) return 50;
  let ratio = (value - low) / span;
  ratio = Math.max(0, Math.min(1, ratio));
  if (invert) ratio = 1 - ratio;
  return ratio * 100;
}

function categoryFor(score: number): string {
  if (score > 70) return CATEGORY_FORTRESS;
  if (score > 50) return CATEGORY_PROMISING;
  if (score > 30) return CATEGORY_AVERAGE;
  return CATEGORY_WEAK;
}

function scoreCompany(row: TasiCompany): { matrix_score: number; category: string } {
  if (row.net_income <= 0) {
    return { matrix_score: -1000, category: CATEGORY_LOSER };
  }
  const growth = clipNorm(row.profit_growth, -20, 40);
  const dividend = clipNorm(row.dividend_yield, 0, 8);
  const roe = clipNorm(row.roe, 0, 30);
  const roa = clipNorm(row.roa, 0, 15);
  const solvency = 0.6 * roe + 0.4 * roa;
  const peScore =
    row.pe_ratio != null && row.pe_ratio > 0 ? clipNorm(row.pe_ratio, 8, 35, true) : 50;
  const matrix_score = Number(
    (growth * GROWTH_WEIGHT + dividend * DIVIDEND_WEIGHT + solvency * SOLVENCY_WEIGHT + peScore * PE_WEIGHT).toFixed(2),
  );
  return { matrix_score, category: categoryFor(matrix_score) };
}

export function rankingFromMarket(rows: TasiCompany[] = TASI_MARKET, source = MARKET_SOURCE): RankingMatrixResponse {
  const data: RankingRow[] = rows.map((row) => {
    const scored = scoreCompany(row);
    return {
      rank: 0,
      symbol: row.symbol,
      name: row.name,
      profit_growth: row.profit_growth,
      dividend_yield: row.dividend_yield,
      roe: row.roe,
      roa: row.roa,
      pe_ratio: row.pe_ratio,
      net_income: row.net_income,
      last_price: row.close,
      volume: row.volume,
      matrix_score: scored.matrix_score,
      category: scored.category,
    };
  }).sort((left, right) => {
    if (right.matrix_score !== left.matrix_score) return right.matrix_score - left.matrix_score;
    return left.symbol.localeCompare(right.symbol);
  });
  data.forEach((row, index) => {
    row.rank = index + 1;
  });
  return {
    success: true,
    total_companies: data.length,
    source,
    data,
  };
}

export function sectorsFromMarket(rows: TasiCompany[] = TASI_MARKET, source = MARKET_SOURCE): SectorRotationResponse {
  const groups = new Map<string, TasiCompany[]>();
  for (const row of rows) {
    const list = groups.get(row.sector) ?? [];
    list.push(row);
    groups.set(row.sector, list);
  }
  const sectors: SectorData[] = [...groups.entries()].map(([sector, rows]) => {
    const total_value_traded = rows.reduce((sum, row) => sum + valueTraded(row), 0);
    const total_volume = rows.reduce((sum, row) => sum + row.volume, 0);
    const net_flow = rows.reduce((sum, row) => sum + netFlow(row), 0);
    const avg_price_change = rows.reduce((sum, row) => sum + row.change_percent, 0) / rows.length;
    return {
      sector,
      total_value_traded,
      avg_price_change: Number(avg_price_change.toFixed(4)),
      total_volume,
      companies_count: rows.length,
      sector_momentum_score: 0,
      status: "",
      net_flow,
      rank: 0,
    };
  });
  const meanValue =
    sectors.reduce((sum, row) => sum + row.total_value_traded, 0) / Math.max(sectors.length, 1);
  for (const row of sectors) {
    const valueFactor = meanValue ? row.total_value_traded / meanValue : 1;
    row.sector_momentum_score = Number((row.avg_price_change * 0.5 + valueFactor * 0.5).toFixed(4));
    row.status =
      row.sector_momentum_score > 2
        ? STATUS_LEADER
        : row.sector_momentum_score > 0
          ? STATUS_ACCUMULATION
          : STATUS_OUTFLOW;
  }
  sectors.sort((left, right) => {
    if (right.sector_momentum_score !== left.sector_momentum_score) {
      return right.sector_momentum_score - left.sector_momentum_score;
    }
    return right.net_flow - left.net_flow;
  });
  sectors.forEach((row, index) => {
    row.rank = index + 1;
  });
  return {
    success: true,
    total_sectors: sectors.length,
    source,
    sectors,
  };
}

function flowStatus(flow: number): string {
  if (flow > 0) return "تدفق داخل 🚀";
  if (flow < 0) return "تدفق خارج ⚠️";
  return "توازن";
}

function canonicalSector(name: string): string {
  const value = name.trim();
  const aliases: Record<string, string> = {
    البنوك: "المصارف",
    Banks: "المصارف",
    Energy: "الطاقة",
    Materials: "المواد الأساسية",
  };
  return aliases[value] ?? value;
}

export function companiesFromMarket(
  sectorName: string,
  rows: TasiCompany[] = TASI_MARKET,
): SectorCompaniesResponse {
  const wanted = canonicalSector(sectorName);
  const companies: SectorCompany[] = rows.filter(
    (row) => canonicalSector(row.sector) === wanted,
  )
    .map((row) => {
      const flow = netFlow(row);
      return {
        symbol: row.symbol,
        name: row.name,
        sector: row.sector,
        last_price: row.close,
        price_change_pct: row.change_percent,
        volume: row.volume,
        value_traded: valueTraded(row),
        net_flow: flow,
        inflow: Math.max(flow, 0),
        outflow: Math.max(-flow, 0),
        flow_status: flowStatus(flow),
        live: true,
      };
    })
    .sort((left, right) => Math.abs(right.net_flow) - Math.abs(left.net_flow));
  return {
    success: true,
    sector: sectorName.trim() || wanted,
    total_companies: companies.length,
    companies,
  };
}

export function recommendationsFromMarket(
  rows: TasiCompany[] = TASI_MARKET,
  source = MARKET_SOURCE,
): RecommendationsResponse {
  const recs: MarketRecommendation[] = [];
  for (const row of rows) {
    if (row.net_income <= 0) continue;
    const atr = row.close * 0.018;
    if (row.change_percent >= 0.3) {
      recs.push({
        symbol: row.symbol,
        name: row.name,
        close_price: row.close,
        signal_type: "استمرار زخم صاعد",
        signal_kind: "momentum",
        confidence: `${Math.min(94, 78 + Math.round(row.change_percent * 6))}%`,
        confidence_score: Math.min(94, 78 + Math.round(row.change_percent * 6)),
        entry_price: row.close.toFixed(2),
        target_price: (row.close + atr * 1.6).toFixed(2),
        stop_loss: (row.close - atr).toFixed(2),
        reason: `إغلاق ${row.close.toFixed(2)} ر.س مع تغير ${row.change_percent}% وحجم ${Math.round(row.volume).toLocaleString("en-US")} — الزخم فوق الجلسة مع سيولة ظاهرة.`,
        volume_ratio: row.volume_ratio,
        mfi: 62,
      });
      continue;
    }
    if (row.change_percent <= -0.1 && row.roe >= 12) {
      recs.push({
        symbol: row.symbol,
        name: row.name,
        close_price: row.close,
        signal_type: "ارتداد إيجابي",
        signal_kind: "bounce",
        confidence: `${Math.min(90, 76 + Math.round(Math.abs(row.change_percent) * 4))}%`,
        confidence_score: Math.min(90, 76 + Math.round(Math.abs(row.change_percent) * 4)),
        entry_price: row.close.toFixed(2),
        target_price: (row.close + atr * 1.4).toFixed(2),
        stop_loss: (row.close - atr * 0.9).toFixed(2),
        reason: `ضغط بيعي محدود (${row.change_percent}%) مع ROE ${row.roe}% — فرصة ارتداد من إغلاق ${row.close.toFixed(2)} ر.س.`,
        volume_ratio: row.volume_ratio,
        mfi: 38,
      });
    }
  }
  recs.sort((left, right) => right.confidence_score - left.confidence_score);
  return {
    success: true,
    count: recs.length,
    source,
    data: recs,
  };
}

export function radarFromMarket(
  symbol: string,
  rows: TasiCompany[] = TASI_MARKET,
  source = MARKET_SOURCE,
): LiveRadarResponse | null {
  const row = companyBySymbol(symbol, rows);
  if (!row) return null;
  const value = valueTraded(row);
  const flow = netFlow(row);
  const sessionRange = row.high > row.low ? row.high - row.low : row.close * 0.018;
  const atr = Number(sessionRange.toFixed(2));
  const vwap = Number(typicalPrice(row).toFixed(2));
  const buyRatio = sessionBuyRatio(row);
  const entry = row.change_percent >= 0.35 && row.volume_ratio >= 0.8;
  const exit = row.change_percent <= -1.2;
  const signal = entry ? "entry" : exit ? "exit" : "neutral";
  return {
    symbol: row.symbol,
    success: true,
    source,
    analysis: {
      symbol: row.symbol,
      signal,
      entry,
      exit,
      trap: null,
      flow_verified: true,
      score: Math.max(35, Math.min(92, 60 + Math.round(row.change_percent * 8))),
      net_flow: flow,
      inflow: Math.max(flow, 0),
      outflow: Math.max(-flow, 0),
      buy_volume: row.volume * buyRatio,
      sell_volume: row.volume * (1 - buyRatio),
      buy_ratio: Number(buyRatio.toFixed(2)),
      sell_ratio: Number((1 - buyRatio).toFixed(2)),
      last_price: row.close,
      vwap,
      atr,
      suggested_entry: Number((row.close * 0.997).toFixed(2)),
      suggested_exit: Number((row.close * 1.028).toFixed(2)),
      target_price: Number((row.close + atr * 1.5).toFixed(2)),
      stop_loss: Number((row.close - atr).toFixed(2)),
      change_percent: row.change_percent,
      trade_count: Math.max(12, Math.round(row.volume / 80_000)),
      reasons: [
        `إغلاق ${row.close.toFixed(2)} ر.س على ${row.name} (${row.change_percent}%)`,
        `قيمة التداول ${(value / 1_000_000).toFixed(1)} مليون ر.س — حجم ${Math.round(row.volume).toLocaleString("en-US")} (${row.volume_ratio.toFixed(2)}× متوسط 20 يوماً)`,
      ],
    },
  };
}
