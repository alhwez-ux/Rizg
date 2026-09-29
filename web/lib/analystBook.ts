import { listedNameFor } from "@/lib/listedCompanies";
import { lockScaledPlan } from "@/lib/liveEntryPlan";
import { isProhibitedStock, isPureStock, shariahStatus } from "@/lib/shariah";
import { isValidLongPlan } from "@/lib/tradeGeometry";
import { TASI_COMPLIANCE_UNIVERSE } from "@/prisma/tasiUniverse";

export interface AnalystBookPick {
  symbol: string;
  houses: string[];
  entry_price: number;
  target_price: number;
  stop_loss: number;
  timeframe: string;
  valid_until: string;
  note?: string;
}

const STATUS_AR: Record<string, string> = {
  PURE: "نقي",
  MIXED: "مختلط",
  PROHIBITED: "محرم",
};

const BY_SYMBOL = new Map(TASI_COMPLIANCE_UNIVERSE.map((item) => [item.symbol, item]));

/** Curated desk book. Not a live scrape of research-house websites. */
export const ANALYST_BOOK: AnalystBookPick[] = [
  {
    symbol: "1120",
    houses: ["الراجحي المالية", "الجزيرة كابيتال"],
    entry_price: 86.4,
    target_price: 94.2,
    stop_loss: 82.5,
    timeframe: "3 أشهر",
    valid_until: "2026-12-31",
    note: "إجماع شراء على السهم النقي",
  },
  {
    symbol: "1140",
    houses: ["البلاد المالية"],
    entry_price: 28.1,
    target_price: 31.5,
    stop_loss: 26.4,
    timeframe: "شهران",
    valid_until: "2026-11-30",
    note: "هدف فوق الدخول ووقف تحته",
  },
  {
    symbol: "1150",
    houses: ["الإنماء للاستثمار", "دراية المالية"],
    entry_price: 27.2,
    target_price: 30.8,
    stop_loss: 25.6,
    timeframe: "6 أسابيع",
    valid_until: "2026-11-15",
    note: "خطة شراء متوسطة",
  },
  {
    symbol: "2222",
    houses: ["الأهلي كابيتال", "الرياض المالية"],
    entry_price: 26.5,
    target_price: 29.4,
    stop_loss: 25.1,
    timeframe: "شهر",
    valid_until: "2026-10-30",
    note: "سهم مختلط — يختفي عند تفعيل فلتر النقي",
  },
  {
    symbol: "4190",
    houses: ["جدوى للاستثمار"],
    entry_price: 140,
    target_price: 152,
    stop_loss: 134,
    timeframe: "منتهية",
    valid_until: "2026-01-15",
    note: "أفق منتهٍ — يجب ألا يظهر",
  },
  {
    symbol: "2010",
    houses: ["الراجحي المالية"],
    entry_price: 64,
    target_price: 61,
    stop_loss: 66.5,
    timeframe: "شهر",
    valid_until: "2026-12-31",
    note: "هندسة مقلوبة — يجب ألا تظهر",
  },
  {
    symbol: "1010",
    houses: ["الرياض المالية"],
    entry_price: 28,
    target_price: 31,
    stop_loss: 26.5,
    timeframe: "شهر",
    valid_until: "2026-12-31",
    note: "محرم — يجب ألا يظهر",
  },
];

export const ANALYST_HINT =
  "يُقفل الدخول على آخر سعر لحظة ظهور الإشارة، ويُحسب الهدف والوقف من ذلك الدخول. آخر السعر يتحرك، ومستويات الخطة تبقى كما قُفلت.";

export function riyadhToday(now = new Date()): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Riyadh",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(now);
}

export function buildAnalystConsensus(
  pureOnly = false,
  today = riyadhToday(),
  lastPrices: Record<string, number> = {},
) {
  const data = ANALYST_BOOK.map((item) => publishPick(item, today, pureOnly, lastPrices[item.symbol])).filter(
    (row) => row != null,
  );
  data.sort((left, right) => {
    const horizon = left.valid_until.localeCompare(right.valid_until);
    if (horizon !== 0) return horizon;
    if (right.reward_ratio !== left.reward_ratio) return right.reward_ratio - left.reward_ratio;
    return left.symbol.localeCompare(right.symbol);
  });
  return {
    success: true,
    source: "curated",
    count: data.length,
    as_of: today,
    hint: ANALYST_HINT,
    data,
  };
}

function publishPick(item: AnalystBookPick, today: string, pureOnly: boolean, live: number | undefined) {
  const symbol = item.symbol.trim().toUpperCase();
  if (!/^[1-8]\d{3}$/.test(symbol) || isProhibitedStock(symbol)) return null;
  if (pureOnly && !isPureStock(symbol)) return null;
  if (!item.valid_until || item.valid_until < today) return null;
  const houses = item.houses.map((name) => name.trim()).filter(Boolean);
  if (!houses.length || !isValidLongPlan(item.entry_price, item.target_price, item.stop_loss)) return null;
  const anchor = live != null && live > 0 ? live : item.entry_price;
  if (!(anchor > 0)) return null;
  const locked = lockScaledPlan(
    "analyst",
    symbol,
    item.valid_until,
    item.entry_price,
    item.target_price,
    item.stop_loss,
    anchor,
  );
  if (!locked) return null;
  const status = shariahStatus(symbol);
  const stock = BY_SYMBOL.get(symbol);
  return {
    symbol,
    name: listedNameFor(symbol) || stock?.companyNameAr || symbol,
    sector: stock?.sector || "",
    houses,
    last_price: Number(anchor.toFixed(2)),
    entry_price: locked.entry_price,
    target_price: locked.target_price,
    stop_loss: locked.stop_loss,
    reward_ratio: locked.reward_ratio,
    timeframe: item.timeframe.trim() || "غير محدد",
    valid_until: item.valid_until,
    note: (item.note || "").trim(),
    entry_locked_at: locked.locked_at,
    shariah_status: status,
    shariah_label: status ? STATUS_AR[status] || "" : "",
  };
}
