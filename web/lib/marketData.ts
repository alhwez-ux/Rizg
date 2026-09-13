/**
 * TASI tape used by the dashboard when the live close feed is unreachable.
 * Price, volume and session range are the 13 Sep 2026 Tadawul close
 * (Yahoo Finance chart, same source as the TASI index chip).
 * Value traded is typical price (high+low+close)/3 × volume.
 * Net income is in million SAR.
 */
export const MARKET_AS_OF = "2026-09-13";
export const MARKET_SOURCE = "تاسي — إغلاق 13 سبتمبر 2026";

export interface TasiCompany {
  symbol: string;
  name: string;
  sector: string;
  close: number;
  change_percent: number;
  volume: number;
  value_traded: number;
  open: number;
  high: number;
  low: number;
  volume_ratio: number;
  pe_ratio: number | null;
  roe: number;
  roa: number;
  dividend_yield: number;
  profit_growth: number;
  net_income: number;
}

export const TASI_MARKET: TasiCompany[] = [
  {
    symbol: "2222",
    name: "أرامكو السعودية",
    sector: "الطاقة",
    close: 25.72,
    change_percent: -1.61,
    volume: 7_258_821,
    value_traded: 187_567_931,
    open: 26.08,
    high: 26.08,
    low: 25.72,
    volume_ratio: 0.95,
    pe_ratio: 15.48,
    roe: 23.75,
    roa: 19.81,
    dividend_yield: 5.13,
    profit_growth: 29.56,
    net_income: 408_370,
  },
  {
    symbol: "1120",
    name: "الراجحي",
    sector: "المصارف",
    close: 65.2,
    change_percent: -1.21,
    volume: 4_662_497,
    value_traded: 304_927_299,
    open: 65.8,
    high: 65.8,
    low: 65.2,
    volume_ratio: 0.67,
    pe_ratio: 15.56,
    roe: 18.52,
    roa: 2.54,
    dividend_yield: 2.53,
    profit_growth: 16.34,
    net_income: 24_980,
  },
  {
    symbol: "1180",
    name: "الأهلي السعودي",
    sector: "المصارف",
    close: 41.22,
    change_percent: -0.91,
    volume: 3_345_943,
    value_traded: 137_785_934,
    open: 41.48,
    high: 41.48,
    low: 40.84,
    volume_ratio: 1.16,
    pe_ratio: 9.84,
    roe: 12.56,
    roa: 2.12,
    dividend_yield: 5.44,
    profit_growth: 12.52,
    net_income: 24_910,
  },
  {
    symbol: "7010",
    name: "الاتصالات السعودية",
    sector: "الاتصالات",
    close: 43.8,
    change_percent: -0.14,
    volume: 1_035_156,
    value_traded: 45_263_921,
    open: 43.86,
    high: 43.88,
    low: 43.5,
    volume_ratio: 0.46,
    pe_ratio: 14.85,
    roe: 17.39,
    roa: 5.9,
    dividend_yield: 5.02,
    profit_growth: 16.11,
    net_income: 14_670,
  },
  {
    symbol: "1150",
    name: "الإنماء",
    sector: "المصارف",
    close: 24.77,
    change_percent: -1.55,
    volume: 4_303_001,
    value_traded: 107_087_351,
    open: 25.04,
    high: 25.16,
    low: 24.73,
    volume_ratio: 0.81,
    pe_ratio: 12.6,
    roe: 13.89,
    roa: 2.1,
    dividend_yield: 3.97,
    profit_growth: 4.88,
    net_income: 5_960,
  },
  {
    symbol: "1211",
    name: "معادن",
    sector: "المواد الأساسية",
    close: 63.9,
    change_percent: -3.18,
    volume: 1_265_000,
    value_traded: 81_466_002,
    open: 65.0,
    high: 65.4,
    low: 63.9,
    volume_ratio: 0.95,
    pe_ratio: 33.33,
    roe: 12.61,
    roa: 5.33,
    dividend_yield: 0,
    profit_growth: 72.15,
    net_income: 7_690,
  },
  {
    symbol: "2010",
    name: "سابك",
    sector: "المواد الأساسية",
    close: 49.5,
    change_percent: -0.6,
    volume: 1_487_218,
    value_traded: 73_478_483,
    open: 49.8,
    high: 49.8,
    low: 48.92,
    volume_ratio: 1.12,
    pe_ratio: null,
    roe: -0.11,
    roa: 1.13,
    dividend_yield: 4.45,
    profit_growth: -233.41,
    net_income: -21_320,
  },
  {
    symbol: "1010",
    name: "بنك الرياض",
    sector: "المصارف",
    close: 20.2,
    change_percent: -0.83,
    volume: 2_534_294,
    value_traded: 51_302_559,
    open: 20.35,
    high: 20.36,
    low: 20.17,
    volume_ratio: 1.06,
    pe_ratio: 8.14,
    roe: 13.88,
    roa: 2.07,
    dividend_yield: 5.07,
    profit_growth: 1.54,
    net_income: 9_970,
  },
  {
    symbol: "2082",
    name: "أكوا باور",
    sector: "المرافق",
    close: 185.1,
    change_percent: -3.04,
    volume: 221_257,
    value_traded: 41_301_307,
    open: 189.9,
    high: 189.9,
    low: 185.0,
    volume_ratio: 0.86,
    pe_ratio: 91.43,
    roe: 6.0,
    roa: 1.76,
    dividend_yield: 0.24,
    profit_growth: -10.46,
    net_income: 1_600,
  },
  {
    symbol: "1140",
    name: "بنك البلاد",
    sector: "المصارف",
    close: 25.1,
    change_percent: -1.34,
    volume: 709_459,
    value_traded: 17_859_448,
    open: 25.34,
    high: 25.34,
    low: 25.08,
    volume_ratio: 0.61,
    pe_ratio: 12.7,
    roe: 13.97,
    roa: 1.79,
    dividend_yield: 4.29,
    profit_growth: 4.18,
    net_income: 2_940,
  },
  {
    symbol: "2280",
    name: "المراعي",
    sector: "إنتاج الأغذية",
    close: 46.88,
    change_percent: -1.76,
    volume: 414_291,
    value_traded: 19_493_773,
    open: 47.7,
    high: 47.78,
    low: 46.5,
    volume_ratio: 0.71,
    pe_ratio: 19.48,
    roe: 12.24,
    roa: 4.78,
    dividend_yield: 2.44,
    profit_growth: 7.6,
    net_income: 2_450,
  },
  {
    symbol: "4190",
    name: "جرير",
    sector: "التجزئة",
    close: 16.29,
    change_percent: 0.8,
    volume: 610_154,
    value_traded: 9_912_969,
    open: 16.2,
    high: 16.29,
    low: 16.16,
    volume_ratio: 0.36,
    pe_ratio: 17.26,
    roe: 67.25,
    roa: 17.65,
    dividend_yield: 5.38,
    profit_growth: 6.86,
    net_income: 1_120,
  },
  {
    symbol: "7203",
    name: "عِلم",
    sector: "البرمجيات والخدمات",
    close: 623.0,
    change_percent: 0.65,
    volume: 61_749,
    value_traded: 38_377_004,
    open: 619.0,
    high: 626.5,
    low: 615.0,
    volume_ratio: 0.68,
    pe_ratio: 22.22,
    roe: 56.09,
    roa: 12.34,
    dividend_yield: 1.64,
    profit_growth: 14.16,
    net_income: 2_170,
  },
  {
    symbol: "4030",
    name: "البحري",
    sector: "النقل",
    close: 35.0,
    change_percent: -4.48,
    volume: 2_305_779,
    value_traded: 80_994_331,
    open: 34.98,
    high: 35.5,
    low: 34.88,
    volume_ratio: 0.92,
    pe_ratio: 5.29,
    roe: 38.24,
    roa: 12.83,
    dividend_yield: 2.76,
    profit_growth: 4.52,
    net_income: 6_390,
  },
];

export function companyBySymbol(symbol: string, rows: TasiCompany[] = TASI_MARKET): TasiCompany | undefined {
  const ticker = symbol.trim().toUpperCase();
  return rows.find((row) => row.symbol === ticker);
}

export function typicalPrice(row: TasiCompany): number {
  if (row.high > 0 && row.low > 0) {
    return (row.high + row.low + row.close) / 3;
  }
  return row.close;
}

export function valueTraded(row: TasiCompany): number {
  if (row.value_traded > 0) return row.value_traded;
  return typicalPrice(row) * row.volume;
}

export function sessionBuyRatio(row: TasiCompany): number {
  const span = row.high - row.low;
  if (!(span > 0)) return row.change_percent >= 0 ? 1 : 0;
  return Math.max(0, Math.min(1, (row.close - row.low) / span));
}

export function netFlow(row: TasiCompany): number {
  return valueTraded(row) * (row.change_percent / 100);
}

/** Value-weighted tape change used when the TASI index quote is unavailable. */
export function tasiTapeChange(rows: TasiCompany[] = TASI_MARKET): number {
  let traded = 0;
  let weighted = 0;
  for (const row of rows) {
    const value = valueTraded(row);
    traded += value;
    weighted += value * row.change_percent;
  }
  return traded ? weighted / traded : 0;
}
