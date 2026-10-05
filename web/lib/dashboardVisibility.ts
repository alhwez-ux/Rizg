export const VISIBILITY_STORAGE_KEY = "rizg-dashboard-visibility";

export const VISIBILITY_KEYS = [
  "shariah",
  "theme",
  "install",
  "auth",
  "password",
  "notifications",
  "stream",
  "search",
  "sessionRow",
  "lastUpdate",
  "underWatch",
  "tabs",
  "matrix",
  "columnEntry",
  "columnExit",
  "columnAccumulation",
  "columnDistribution",
  "heatmap",
  "followedRadar",
  "opportunitiesDaily",
  "opportunitiesReco",
  "opportunitiesFlow",
  "toolPreopen",
  "toolFunds",
  "toolAnalysts",
  "toolRecovery",
  "toolDividends",
  "toolRanking",
] as const;

export type VisibilityKey = (typeof VISIBILITY_KEYS)[number];
export type VisibilityMap = Record<VisibilityKey, boolean>;

const HIDDEN_BY_DEFAULT = new Set<VisibilityKey>(["heatmap"]);

export const VISIBILITY_DEFAULTS: VisibilityMap = Object.fromEntries(
  VISIBILITY_KEYS.map((key) => [key, !HIDDEN_BY_DEFAULT.has(key)]),
) as VisibilityMap;

export interface VisibilityItem {
  key: VisibilityKey;
  label: string;
}

export interface VisibilityGroup {
  title: string;
  items: VisibilityItem[];
}

export const VISIBILITY_GROUPS: VisibilityGroup[] = [
  {
    title: "رأس الشاشة",
    items: [
      { key: "shariah", label: "الأسهم النقية والمختلطة" },
      { key: "theme", label: "وضع النهار والليل" },
      { key: "install", label: "تثبيت التطبيق" },
      { key: "auth", label: "الخروج" },
      { key: "password", label: "تعديل الرقم السري" },
      { key: "notifications", label: "التنبيهات" },
      { key: "stream", label: "تدفق بيانات" },
      { key: "search", label: "بحث الشركة والمتابعة" },
      { key: "sessionRow", label: "تحديث الجلسة وتتبعها" },
      { key: "lastUpdate", label: "تاريخ ووقت آخر تحديث" },
      { key: "underWatch", label: "شركات تحت المراقبة" },
      { key: "tabs", label: "تبويبات الشاشة" },
    ],
  },
  {
    title: "المصفوفة المؤسسية",
    items: [
      { key: "matrix", label: "المصفوفة" },
      { key: "columnEntry", label: "عمود الدخول" },
      { key: "columnExit", label: "عمود الخروج" },
      { key: "columnAccumulation", label: "عمود التجميع" },
      { key: "columnDistribution", label: "عمود التصريف" },
    ],
  },
  {
    title: "الشاشة الرئيسية",
    items: [
      { key: "heatmap", label: "خريطة السيولة القطاعية" },
      { key: "followedRadar", label: "رادار الأسهم المتابعة" },
    ],
  },
  {
    title: "الفرص والسيولة",
    items: [
      { key: "opportunitiesDaily", label: "فرص الجلسة" },
      { key: "opportunitiesReco", label: "توصيات الإغلاق" },
      { key: "opportunitiesFlow", label: "السيولة اليومية" },
    ],
  },
  {
    title: "الأدوات",
    items: [
      { key: "toolPreopen", label: "ما قبل الافتتاح" },
      { key: "toolFunds", label: "الصناديق" },
      { key: "toolAnalysts", label: "بيوت الخبرة" },
      { key: "toolRecovery", label: "حاسبة التعديل" },
      { key: "toolDividends", label: "التوزيعات" },
      { key: "toolRanking", label: "تصنيف الشركات" },
    ],
  },
];

export function readVisibility(raw: string | null): VisibilityMap {
  const next = { ...VISIBILITY_DEFAULTS };
  if (!raw) return next;
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (!parsed || typeof parsed !== "object") return next;
    const record = parsed as Record<string, unknown>;
    for (const key of VISIBILITY_KEYS) {
      if (typeof record[key] === "boolean") next[key] = record[key];
    }
  } catch {
    return { ...VISIBILITY_DEFAULTS };
  }
  return next;
}
