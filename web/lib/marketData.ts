/**
 * TASI tape used by the dashboard when the Python API is unreachable.
 * Figures are the 10 Sep 2026 Tadawul close (S&P Global via stockanalysis,
 * cross-checked with TradingView / Arincen). Net income is in million SAR.
 */
export const MARKET_AS_OF = "2026-09-10";
export const MARKET_SOURCE = "تاسي — إغلاق 10 سبتمبر 2026";

export interface TasiCompany {
  symbol: string;
  name: string;
  sector: string;
  close: number;
  change_percent: number;
  volume: number;
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
    close: 26.14,
    change_percent: 0.38,
    volume: 4_536_304,
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
    close: 66.0,
    change_percent: -0.15,
    volume: 8_478_340,
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
    close: 41.6,
    change_percent: -0.24,
    volume: 2_894_363,
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
    close: 43.86,
    change_percent: 0.83,
    volume: 1_253_686,
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
    close: 25.16,
    change_percent: 0,
    volume: 2_824_483,
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
    close: 66.0,
    change_percent: -1.05,
    volume: 968_260,
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
    close: 49.8,
    change_percent: 0.65,
    volume: 1_207_016,
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
    close: 20.37,
    change_percent: -1.36,
    volume: 2_380_000,
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
    close: 190.9,
    change_percent: -0.62,
    volume: 164_370,
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
    close: 25.44,
    change_percent: -0.7,
    volume: 1_166_547,
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
    close: 47.72,
    change_percent: -0.04,
    volume: 601_817,
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
    close: 16.16,
    change_percent: -1.76,
    volume: 1_667_348,
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
    close: 619.0,
    change_percent: 0.41,
    volume: 87_607,
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
    close: 36.64,
    change_percent: 1.27,
    volume: 2_615_581,
    pe_ratio: 5.29,
    roe: 38.24,
    roa: 12.83,
    dividend_yield: 2.76,
    profit_growth: 4.52,
    net_income: 6_390,
  },
];

export function companyBySymbol(symbol: string): TasiCompany | undefined {
  const ticker = symbol.trim().toUpperCase();
  return TASI_MARKET.find((row) => row.symbol === ticker);
}

export function valueTraded(row: TasiCompany): number {
  return row.close * row.volume;
}

export function netFlow(row: TasiCompany): number {
  return valueTraded(row) * (row.change_percent / 100);
}

/** Value-weighted tape change used when the TASI index quote is unavailable. */
export function tasiTapeChange(): number {
  let traded = 0;
  let weighted = 0;
  for (const row of TASI_MARKET) {
    const value = valueTraded(row);
    traded += value;
    weighted += value * row.change_percent;
  }
  return traded ? weighted / traded : 0;
}
