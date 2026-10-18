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
  published_on?: string;
  weight?: number;
  stance?: string;
}

const EXIT_STANCES = new Set(["sell", "exit", "caution", "avoid"]);

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

export function buildRollingConsensus(
  pureOnly = false,
  today = riyadhToday(),
  lastPrices: Record<string, number> = {},
  windowDays = 5,
) {
  const span = Math.max(1, Math.min(windowDays, 30));
  const data = buildRollingSide(pureOnly, today, lastPrices, span, "buy").data;
  const exits = buildRollingSide(pureOnly, today, lastPrices, span, "exit").data;
  return {
    success: true,
    source: "curated",
    count: data.length,
    exit_count: exits.length,
    as_of: today,
    window_days: span,
    hint: `توصيات مؤرخة خلال آخر ${span} أيام: دخول عندما يغلب الشراء، وتخارج عندما تُسجَّل توصية حذر أو خروج. بلا تاريخ نشر لا تظهر التوصية. المستويات تبقى أرقام التقارير، والسعر الحالي من التسعير الحي إن وُجد.`,
    data,
    exits,
  };
}

function byConsensus(left: { consensus_strength: number; analyst_count: number; symbol: string }, right: { consensus_strength: number; analyst_count: number; symbol: string }) {
  if (right.consensus_strength !== left.consensus_strength) return right.consensus_strength - left.consensus_strength;
  if (right.analyst_count !== left.analyst_count) return right.analyst_count - left.analyst_count;
  return left.symbol.localeCompare(right.symbol);
}

function buildRollingSide(
  pureOnly: boolean,
  today: string,
  lastPrices: Record<string, number>,
  span: number,
  side: "buy" | "exit",
) {
  const start = shiftIsoDate(today, -(span - 1));
  const grouped = new Map<string, Map<string, ReportPlan>>();
  for (const item of ANALYST_BOOK) {
    const plans = reportPlans(item, today, start, pureOnly, side);
    if (!plans) continue;
    const houses = grouped.get(plans.symbol) ?? new Map<string, ReportPlan>();
    for (const plan of plans.plans) {
      const previous = houses.get(plan.house);
      if (!previous || plan.published_on >= previous.published_on) houses.set(plan.house, plan);
    }
    grouped.set(plans.symbol, houses);
  }
  const data = [...grouped.entries()].map(([symbol, houses]) => consensusRow(symbol, [...houses.values()], lastPrices[symbol], span, side));
  data.sort(byConsensus);
  return { data };
}

function shiftIsoDate(iso: string, days: number): string {
  const [year, month, day] = iso.split("-").map((part) => Number(part));
  const stamp = new Date(Date.UTC(year, month - 1, day));
  stamp.setUTCDate(stamp.getUTCDate() + days);
  return stamp.toISOString().slice(0, 10);
}

interface ReportPlan {
  house: string;
  published_on: string;
  weight: number;
  entry: number | null;
  target: number | null;
  stop: number | null;
  note: string;
}

function isValidExitPlan(entry: number, target: number, stop: number): boolean {
  return Number.isFinite(entry) && Number.isFinite(target) && Number.isFinite(stop) && target > 0 && target < entry && entry < stop;
}

function reportPlans(item: AnalystBookPick, today: string, start: string, pureOnly: boolean, side: "buy" | "exit" = "buy") {
  const symbol = item.symbol.trim().toUpperCase();
  if (!/^[1-8]\d{3}$/.test(symbol) || isProhibitedStock(symbol)) return null;
  if (pureOnly && !isPureStock(symbol)) return null;
  const stance = (item.stance || (side === "buy" ? "buy" : "")).trim().toLowerCase();
  if (side === "exit" ? !EXIT_STANCES.has(stance) : stance !== "buy" && stance !== "entry") return null;
  const published = (item.published_on || "").slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(published) || published < start || published > today) return null;
  const houses = item.houses.map((name) => name.trim()).filter(Boolean);
  if (!houses.length) return null;
  const note = (item.note || "").trim();
  const supplied = [item.entry_price, item.target_price, item.stop_loss].map((value) => value != null && String(value).trim() !== "");
  let entry: number | null = null;
  let target: number | null = null;
  let stop: number | null = null;
  if (side === "buy") {
    if (!isValidLongPlan(item.entry_price, item.target_price, item.stop_loss)) return null;
    entry = item.entry_price;
    target = item.target_price;
    stop = item.stop_loss;
  } else if (supplied.some(Boolean) && !supplied.every(Boolean)) {
    return null;
  } else if (supplied.every(Boolean)) {
    if (!isValidExitPlan(item.entry_price, item.target_price, item.stop_loss)) return null;
    entry = item.entry_price;
    target = item.target_price;
    stop = item.stop_loss;
  } else if (!note) {
    return null;
  }
  const weight = item.weight != null && item.weight > 0 ? item.weight : 1;
  return {
    symbol,
    plans: houses.map((house) => ({
      house,
      published_on: published,
      weight,
      entry,
      target,
      stop,
      note,
    })),
  };
}

function reportExitReward(entryLow: number, entryHigh: number, targetHigh: number, stopLow: number): number {
  const risk = stopLow - entryHigh;
  const reward = entryLow - targetHigh;
  if (!(risk > 0) || !(reward > 0)) return 0;
  return Number((reward / risk).toFixed(2));
}

function reportReward(entry: number, target: number, stop: number): number {
  const risk = entry - stop;
  if (!(entry > 0) || !(target > 0) || !(stop > 0) || risk <= 0) return 0;
  return Number(((target - entry) / risk).toFixed(2));
}

function consensusRow(symbol: string, plans: ReportPlan[], live: number | undefined, windowDays: number, direction: "buy" | "exit" = "buy") {
  const priced = plans.filter((plan) => plan.entry != null && plan.target != null && plan.stop != null);
  const entries = priced.map((plan) => plan.entry as number);
  const targets = priced.map((plan) => plan.target as number);
  const stops = priced.map((plan) => plan.stop as number);
  const status = shariahStatus(symbol);
  const stock = BY_SYMBOL.get(symbol);
  const money = (value: number) => value.toFixed(2);
  const pricedRow = entries.length
    ? {
        entry_price: money(Math.min(...entries)),
        entry_low: money(Math.min(...entries)),
        entry_high: money(Math.max(...entries)),
        target_price: money(direction === "buy" ? Math.max(...targets) : Math.min(...targets)),
        target_low: money(Math.min(...targets)),
        target_high: money(Math.max(...targets)),
        stop_loss: money(direction === "buy" ? Math.min(...stops) : Math.max(...stops)),
        stop_low: money(Math.min(...stops)),
        stop_high: money(Math.max(...stops)),
        reward_ratio:
          direction === "buy"
            ? reportReward(Math.min(...entries), Math.max(...targets), Math.min(...stops))
            : reportExitReward(Math.min(...entries), Math.max(...entries), Math.max(...targets), Math.min(...stops)),
      }
    : {
        entry_price: "",
        entry_low: "",
        entry_high: "",
        target_price: "",
        target_low: "",
        target_high: "",
        stop_loss: "",
        stop_low: "",
        stop_high: "",
        reward_ratio: 0,
      };
  return {
    symbol,
    name: listedNameFor(symbol) || stock?.companyNameAr || symbol,
    sector: stock?.sector || "",
    houses: plans.map((plan) => plan.house),
    analyst_count: plans.length,
    consensus_strength: Number(plans.reduce((sum, plan) => sum + plan.weight, 0).toFixed(2)),
    direction,
    published_on: plans.map((plan) => plan.published_on).sort().at(-1) || "",
    window_days: windowDays,
    last_price: live != null && live > 0 ? Number(live.toFixed(2)) : null,
    ...pricedRow,
    timeframe: `${windowDays} أيام`,
    valid_until: plans.map((plan) => plan.published_on).sort().at(-1) || "",
    note: plans.find((plan) => plan.note)?.note || "",
    entry_locked_at: null,
    shariah_status: status,
    shariah_label: status ? STATUS_AR[status] || "" : "",
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
