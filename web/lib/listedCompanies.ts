import listedNames from "@/prisma/tasi-listed-names.json";

export interface ListedCompany {
  symbol: string;
  name: string;
}

const ARABIC_DIGITS = "٠١٢٣٤٥٦٧٨٩";

function latinDigits(value: string): string {
  return value.replace(/[٠-٩]/g, (digit) => String(ARABIC_DIGITS.indexOf(digit)));
}

function normQuery(value: string): string {
  let text = latinDigits(value).trim().replace(/[أإآٱ]/g, "ا");
  text = text.replace(/[\s\-_./]+/g, "").replace(/ة/g, "ه").replace(/ى/g, "ي");
  if (text.startsWith("ال") && text.length > 3) text = text.slice(2);
  return text.toLowerCase();
}

const LISTED: ListedCompany[] = Object.entries(listedNames as Record<string, string>).map(([symbol, name]) => ({
  symbol,
  name,
}));

const BY_SYMBOL = new Map(LISTED.map((item) => [item.symbol, item.name]));

export function listedNameFor(symbol: string): string {
  const ticker = latinDigits(symbol).trim().toUpperCase();
  return BY_SYMBOL.get(ticker) || "";
}

export function displayCompanyTitle(symbol: string, fallbackName?: string): string {
  const ticker = latinDigits(symbol).trim().toUpperCase();
  const listed = listedNameFor(ticker);
  const fallback = (fallbackName || "").trim();
  if (listed) return listed;
  if (fallback && fallback !== ticker && !/^\d{4}$/.test(fallback)) return fallback;
  return "";
}

export function searchListedCompanies(query: string, limit = 8): ListedCompany[] {
  const needle = normQuery(query);
  if (!needle || needle.length < 2) return [];
  const ranked: Array<{ score: number; item: ListedCompany }> = [];
  for (const item of LISTED) {
    const nameKey = normQuery(item.name);
    const symbolKey = item.symbol;
    if (needle === symbolKey || needle === nameKey) ranked.push({ score: 0, item });
    else if (symbolKey.startsWith(needle) || nameKey.startsWith(needle)) ranked.push({ score: 1, item });
    else if (`${symbolKey}${nameKey}`.includes(needle)) ranked.push({ score: 2, item });
  }
  ranked.sort((left, right) => left.score - right.score || left.item.name.length - right.item.name.length);
  const seen = new Set<string>();
  const matches: ListedCompany[] = [];
  for (const row of ranked) {
    if (seen.has(row.item.symbol)) continue;
    seen.add(row.item.symbol);
    matches.push(row.item);
    if (matches.length >= limit) break;
  }
  return matches;
}

export function resolveListedCompany(query: string): ListedCompany | null {
  const raw = query.trim();
  if (!raw) return null;
  const ticker = latinDigits(raw).toUpperCase();
  if (/^\d{4}$/.test(ticker)) {
    return { symbol: ticker, name: listedNameFor(ticker) || ticker };
  }
  const matches = searchListedCompanies(raw, 8);
  if (matches.length === 1) return matches[0];
  const exact = matches.filter((item) => normQuery(item.name) === normQuery(raw) || item.name === raw);
  return exact.length === 1 ? exact[0] : null;
}
