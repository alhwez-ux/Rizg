import { TASI_COMPLIANCE_UNIVERSE, type ComplianceStatusLabel, type UniverseStock } from "../prisma/tasiUniverse";

export type ShariahFilter = "all" | "pure";

const MAX_DEBT_RATIO = 0.33;
const MAX_INTEREST_SECURITIES = 0.33;
const MAX_IMPURE_INCOME = 0.05;
const PURE_DEBT_RATIO = 0.12;
const PURE_IMPURE_INCOME = 0.005;

const BY_SYMBOL = new Map(TASI_COMPLIANCE_UNIVERSE.map((item) => [item.symbol, item]));

export function classifyShariah(item: Pick<UniverseStock, "currentStatus" | "debtRatio" | "impureIncomeRatio">): ComplianceStatusLabel {
  if (item.currentStatus === "PROHIBITED") return "PROHIBITED";
  const impure = item.impureIncomeRatio ?? 0;
  const debt = item.debtRatio ?? 0;
  if (impure > MAX_IMPURE_INCOME || debt > MAX_DEBT_RATIO) return "PROHIBITED";
  if (impure <= PURE_IMPURE_INCOME && debt <= PURE_DEBT_RATIO) return "PURE";
  return "MIXED";
}

export function shariahStatus(symbol: string): ComplianceStatusLabel | null {
  const ticker = symbol.trim().toUpperCase();
  const item = BY_SYMBOL.get(ticker);
  return item ? classifyShariah(item) : null;
}

export function isPureStock(symbol: string): boolean {
  return shariahStatus(symbol) === "PURE";
}

export function isProhibitedStock(symbol: string): boolean {
  return shariahStatus(symbol) === "PROHIBITED";
}

export function passesShariahFilter(symbol: string, mode: ShariahFilter): boolean {
  if (isProhibitedStock(symbol)) return false;
  if (mode === "pure") return isPureStock(symbol);
  return true;
}

export function parseShariahFilter(value: string | null | undefined): ShariahFilter {
  return value === "pure" || value === "نقي" ? "pure" : "all";
}

export { MAX_DEBT_RATIO, MAX_IMPURE_INCOME, MAX_INTEREST_SECURITIES };
