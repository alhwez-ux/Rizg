/** Shariah screening status used to decide radar eligibility. */
export type ComplianceStatus = "PURE" | "MIXED" | "PROHIBITED";

export type FinancialGrade = "A" | "B" | "C" | "D" | "E";

/** Statuses allowed on the liquidity radar. PROHIBITED is never queried. */
export const RADAR_ELIGIBLE_STATUSES: readonly ["PURE", "MIXED"] = ["PURE", "MIXED"];

export interface CashDividend {
  announcementDate: string;
  eligibilityDate: string;
  distributionDate: string;
  amountPerShare: number;
}

export interface Stock {
  symbol: string;
  companyNameAr: string;
  companyNameEn: string;
  currentStatus: ComplianceStatus;
  sector: string;
  updatedAt: Date;
  financialGrade?: FinancialGrade;
}

export interface ComplianceHistory {
  quarter: string;
  status: ComplianceStatus;
  purificationRate: number;
  debtRatio: number;
  impureIncomeRatio: number;
}

/** Radar table row: eligible stock plus the latest purification snapshot. */
export interface RadarTableRow {
  symbol: string;
  companyNameAr: string;
  companyNameEn: string;
  currentStatus: "PURE" | "MIXED";
  sector: string;
  updatedAt: Date;
  quarter: string | null;
  purificationRate: number | null;
  debtRatio: number | null;
  impureIncomeRatio: number | null;
  financialGrade: FinancialGrade;
  gradeScore: number;
  gradeSolvency: number;
  gradeDividends: number;
  gradeValuation: number;
  gradeGrowth: number;
  peRatio: number | null;
  pbRatio: number | null;
  dividendYield: number | null;
  revenueGrowth: number | null;
  operatingGrowth: number | null;
  netIncomeMargin: number | null;
  isLosing: boolean;
  lossReason: string | null;
  rsi: number | null;
  ema50: number | null;
  ema200: number | null;
  macd: number | null;
  avgVolume: number | null;
  nextDividend: CashDividend | null;
  dividends: CashDividend[];
}

export function isRadarEligibleStatus(
  status: ComplianceStatus | string | null | undefined,
): status is "PURE" | "MIXED" {
  return status === "PURE" || status === "MIXED";
}

export function isProhibitedStatus(status: ComplianceStatus | string | null | undefined): boolean {
  return status === "PROHIBITED";
}

function parseGrade(value: unknown): FinancialGrade {
  return value === "A" || value === "B" || value === "C" || value === "D" || value === "E" ? value : "C";
}

export function toRadarTableRow(stock: Stock, history: ComplianceHistory | null): RadarTableRow | null {
  if (!isRadarEligibleStatus(stock.currentStatus)) return null;
  return {
    symbol: stock.symbol,
    companyNameAr: stock.companyNameAr,
    companyNameEn: stock.companyNameEn,
    currentStatus: stock.currentStatus,
    sector: stock.sector,
    updatedAt: stock.updatedAt,
    quarter: history?.quarter ?? null,
    purificationRate: history?.purificationRate ?? null,
    debtRatio: history?.debtRatio ?? null,
    impureIncomeRatio: history?.impureIncomeRatio ?? null,
    financialGrade: parseGrade(stock.financialGrade),
    gradeScore: 50,
    gradeSolvency: 50,
    gradeDividends: 50,
    gradeValuation: 50,
    gradeGrowth: 50,
    peRatio: null,
    pbRatio: null,
    dividendYield: null,
    revenueGrowth: null,
    operatingGrowth: null,
    netIncomeMargin: null,
    isLosing: false,
    lossReason: null,
    rsi: null,
    ema50: null,
    ema200: null,
    macd: null,
    avgVolume: null,
    nextDividend: null,
    dividends: [],
  };
}
