"use client";

import { useEffect, useMemo, useState } from "react";
import { apiFetch } from "@/lib/api";
import { ar } from "@/lib/ar";
import type { AnalystPickRow } from "@/lib/analystConsensus";
import type { DailyOpportunityRow } from "@/lib/dailyOpportunities";
import type { DigitalTapeRow } from "@/lib/digitalDesk";
import { useCorrectionRadar } from "@/hooks/useCorrectionRadar";
import { useDigitalTape } from "@/hooks/useDigitalTape";
import { useTasiIndex } from "@/hooks/useTasiIndex";
import { formatCompact, formatMoney, formatPercent, formatPrice } from "@/lib/liquidity";
import type { LiquidityGrade } from "@/lib/dailyLiquidity";
import { fetchRankingMatrix, type RankingRow } from "@/lib/rankingMatrix";
import { passesShariahFilter, shariahStatus, type ShariahFilter } from "@/lib/shariah";

type FilterId = "all" | "pure" | "opportunities" | "consensus";
type SortKey =
  | "name"
  | "price"
  | "change"
  | "path"
  | "cloud"
  | "grade"
  | "funds"
  | "shariah"
  | "health"
  | "analysts";

const FILTERS: { id: FilterId; label: string }[] = [
  { id: "all", label: ar.digitalAll },
  { id: "pure", label: ar.digitalPure },
  { id: "opportunities", label: ar.digitalOpportunities },
  { id: "consensus", label: ar.digitalConsensus },
];

type NewsItem = {
  title: string;
  url: string;
  source?: string;
  published_at?: string;
  companies?: { symbol: string; name: string }[];
};

const PATH_RANK = { up: 3, range: 2, down: 1 } as const;
const GRADE_RANK: Record<LiquidityGrade, number> = { A: 4, B: 3, C: 2, D: 1 };

function gradesFor(rows: DigitalTapeRow[]): Map<string, LiquidityGrade> {
  const measured = rows.filter((row) => row.netFlow != null);
  const winners = measured
    .filter((row) => (row.netFlow ?? 0) > 0)
    .sort((left, right) => (right.netFlow ?? 0) - (left.netFlow ?? 0));
  const aCount = winners.length ? Math.max(1, Math.ceil(winners.length * 0.2)) : 0;
  const bCount = winners.length ? Math.max(aCount, Math.ceil(winners.length * 0.5)) : 0;
  const gradeA = new Set(winners.slice(0, aCount).map((row) => row.symbol));
  const gradeB = new Set(winners.slice(0, bCount).map((row) => row.symbol));
  const grades = new Map<string, LiquidityGrade>();
  for (const row of measured) {
    const flow = row.netFlow ?? 0;
    if (flow <= 0) grades.set(row.symbol, "D");
    else if (gradeA.has(row.symbol)) grades.set(row.symbol, "A");
    else if (gradeB.has(row.symbol)) grades.set(row.symbol, "B");
    else grades.set(row.symbol, "C");
  }
  return grades;
}

function gradeLabel(grade: LiquidityGrade | undefined): string {
  if (grade === "A") return ar.flowGradeA;
  if (grade === "B") return ar.flowGradeB;
  if (grade === "C") return ar.flowGradeC;
  if (grade === "D") return ar.flowGradeD;
  return "—";
}

function pathLabel(path: DigitalTapeRow["path"]): string {
  if (path === "up") return `${ar.ichimokuUp} 🟢`;
  if (path === "down") return `${ar.ichimokuDown} 🔴`;
  if (path === "range") return `${ar.ichimokuRange} 🟡`;
  return "—";
}

function cloudLabel(row: DigitalTapeRow): string {
  const place =
    row.cloud === "above" ? ar.cloudAbove : row.cloud === "inside" ? ar.cloudInside : row.cloud === "below" ? ar.cloudBelow : "";
  const cross =
    row.cloudSignal === "entry"
      ? ar.ichimokuEntry
      : row.cloudSignal === "exit"
        ? ar.ichimokuExit
        : row.cloudSignal === "watch"
          ? ar.ichimokuWatch
          : "";
  if (place && cross) return `${place} · ${cross}`;
  return place || cross || "—";
}

function shariahLabel(symbol: string): string {
  const status = shariahStatus(symbol);
  if (status === "PURE") return ar.dossierPure;
  if (status === "MIXED") return ar.dossierMixed;
  if (status === "PROHIBITED") return ar.dossierProhibited;
  return "—";
}

function fundsLabel(row: DigitalTapeRow): string {
  const parts: string[] = [];
  if (row.blocks != null && row.blocks > 0) {
    const title = row.blockSide === "buy" ? ar.fundsEntry : row.blockSide === "sell" ? ar.fundsExit : ar.fundsBlock;
    parts.push(`${title} ${formatCompact(row.blocks, 0)}`);
  }
  if (row.institutionalMfi != null) parts.push(`MFI ${Math.round(row.institutionalMfi)}%`);
  if (row.hiddenAccumulation) parts.push(ar.fundsHidden);
  if (row.signal === "entry") parts.push(ar.radarStatusEntry);
  else if (row.signal === "exit") parts.push(ar.radarStatusExit);
  return parts.length ? parts.join(" · ") : "—";
}

function healthLabel(category: string | undefined, vwap: number | null): string {
  const fair = vwap != null && vwap > 0 ? formatPrice(vwap) : "";
  if (category && fair) return `${category} · ${fair}`;
  return category || fair || "—";
}

function analystLabel(pick: AnalystPickRow | undefined): string {
  if (!pick) return "—";
  const stance = pick.direction === "exit" ? ar.analystExitBadge : ar.analystEntryBadge;
  return pick.analyst_count > 1 ? `${stance} · ${pick.consensus_strength}` : stance;
}

export function DigitalDesk({
  shariah,
  buys,
  exits,
  opportunities,
  live,
  onBack,
  onOpen,
}: {
  live: boolean;
  shariah: ShariahFilter;
  buys: AnalystPickRow[];
  exits: AnalystPickRow[];
  opportunities: DailyOpportunityRow[];
  onBack: () => void;
  onOpen: (company: { symbol: string; name: string }) => void;
}) {
  const tape = useDigitalTape(live);
  const index = useTasiIndex();
  const correction = useCorrectionRadar(live);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<FilterId>("all");
  const [sortKey, setSortKey] = useState<SortKey>("grade");
  const [sortDesc, setSortDesc] = useState(true);
  const [ranks, setRanks] = useState<RankingRow[]>([]);

  useEffect(() => {
    if (!live) return;
    let active = true;
    const pull = () => {
      fetchRankingMatrix()
        .then((payload) => {
          if (active && payload.data.length) setRanks(payload.data);
        })
        .catch(() => undefined);
    };
    pull();
    const timer = window.setInterval(pull, 5 * 60_000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [live]);

  const grades = useMemo(() => gradesFor(tape.rows), [tape.rows]);
  const health = useMemo(() => {
    const map = new Map<string, string>();
    for (const row of ranks) {
      const category = row.category || "";
      if (!category || category.includes("تكرتشارت")) continue;
      map.set(row.symbol, category);
    }
    return map;
  }, [ranks]);
  const lamps = useMemo(() => {
    const map = new Map<string, "approach" | "rebound">();
    for (const row of correction.rows) map.set(row.symbol, row.signal_kind);
    return map;
  }, [correction.rows]);
  const analysts = useMemo(() => {
    const map = new Map<string, AnalystPickRow>();
    for (const row of buys) map.set(row.symbol, row);
    for (const row of exits) {
      if (!map.has(row.symbol)) map.set(row.symbol, row);
    }
    return map;
  }, [buys, exits]);
  const opportunitySet = useMemo(() => new Set(opportunities.map((row) => row.symbol)), [opportunities]);

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const rows = tape.rows.filter((row) => {
      if (!passesShariahFilter(row.symbol, shariah)) return false;
      if (filter === "pure" && !passesShariahFilter(row.symbol, "pure")) return false;
      if (filter === "opportunities" && !opportunitySet.has(row.symbol)) return false;
      if (filter === "consensus" && !analysts.has(row.symbol)) return false;
      if (!needle) return true;
      return row.symbol.includes(needle) || row.name.toLowerCase().includes(needle);
    });
    const numberOf = (row: DigitalTapeRow): number | null => {
      if (sortKey === "price") return row.price;
      if (sortKey === "change") return row.change;
      if (sortKey === "path") return row.path ? PATH_RANK[row.path] : null;
      if (sortKey === "cloud") return row.cloud === "above" ? 3 : row.cloud === "inside" ? 2 : row.cloud === "below" ? 1 : null;
      if (sortKey === "grade") {
        const grade = grades.get(row.symbol);
        return grade ? GRADE_RANK[grade] : null;
      }
      if (sortKey === "funds") return row.blocks ?? row.institutionalMfi;
      if (sortKey === "shariah") {
        const status = shariahStatus(row.symbol);
        return status === "PURE" ? 3 : status === "MIXED" ? 2 : status === "PROHIBITED" ? 1 : null;
      }
      if (sortKey === "health") return row.vwap;
      if (sortKey === "analysts") return analysts.get(row.symbol)?.consensus_strength ?? null;
      return null;
    };
    rows.sort((left, right) => {
      if (sortKey === "name" || sortKey === "health") {
        const leftText = sortKey === "name" ? left.name : health.get(left.symbol) || "";
        const rightText = sortKey === "name" ? right.name : health.get(right.symbol) || "";
        if (!leftText && !rightText) return left.symbol.localeCompare(right.symbol);
        if (!leftText) return 1;
        if (!rightText) return -1;
        const order = leftText.localeCompare(rightText, "ar");
        return sortDesc ? -order : order;
      }
      const a = numberOf(left);
      const b = numberOf(right);
      if (a == null && b == null) return left.symbol.localeCompare(right.symbol);
      if (a == null) return 1;
      if (b == null) return -1;
      if (a === b) return left.symbol.localeCompare(right.symbol);
      return sortDesc ? b - a : a - b;
    });
    return rows;
  }, [analysts, filter, grades, health, lamps, opportunitySet, query, shariah, sortDesc, sortKey, tape.rows]);

  const chooseSort = (key: SortKey) => {
    if (sortKey === key) setSortDesc((value) => !value);
    else {
      setSortKey(key);
      setSortDesc(key !== "name");
    }
  };

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <button
          type="button"
          onClick={onBack}
          className="rounded-full border border-emerald-400/40 bg-emerald-500/15 px-4 py-2 text-sm font-bold text-emerald-100 transition hover:bg-emerald-500/25"
        >
          {ar.digitalBack}
        </button>
        {tape.stale ? <span className="text-xs text-amber-300">{ar.digitalStale}</span> : null}
      </div>
      <InfluentialNews live={live} onOpen={onOpen} />
      <ResilientNames rows={tape.rows} indexChange={index.quote.changePercent ?? index.quote.change} onOpen={onOpen} />

      <div className="flex flex-wrap items-center gap-2">
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder={ar.digitalSearch}
          className="min-w-[12rem] flex-1 rounded-xl border border-white/10 bg-zinc-950/70 px-3 py-2 text-sm text-zinc-100 outline-none placeholder:text-zinc-500"
        />
        {FILTERS.map((item) => (
          <button
            key={item.id}
            type="button"
            aria-pressed={filter === item.id}
            onClick={() => setFilter(item.id)}
            className={`rounded-full px-3 py-1.5 text-xs font-bold ${
              filter === item.id ? "bg-white text-zinc-950" : "border border-white/10 text-zinc-300"
            }`}
          >
            {item.label} {filterCount(item.id, tape.rows, shariah, query, opportunitySet, analysts)}
          </button>
        ))}
      </div>

      {!tape.ready && tape.rows.length === 0 ? (
        <p className="py-10 text-center text-sm text-zinc-400">{ar.digitalLoading}</p>
      ) : visible.length === 0 ? (
        <p className="py-10 text-center text-sm text-zinc-500">{ar.digitalEmpty}</p>
      ) : (
        <div className="overflow-x-auto rounded-2xl border border-white/10">
          <table className="min-w-[76rem] w-full border-collapse text-right text-sm">
            <thead className="sticky top-0 bg-zinc-950/95 text-xs text-zinc-400">
              <tr>
                <SortHead label={ar.colCompany} active={sortKey === "name"} desc={sortDesc} onClick={() => chooseSort("name")} />
                <SortHead label={ar.colPrice} active={sortKey === "price"} desc={sortDesc} onClick={() => chooseSort("price")} />
                <SortHead label={ar.colChange} active={sortKey === "change"} desc={sortDesc} onClick={() => chooseSort("change")} />
                <SortHead label={ar.colPath} active={sortKey === "path"} desc={sortDesc} onClick={() => chooseSort("path")} />
                <SortHead label={ar.colCloud} active={sortKey === "cloud"} desc={sortDesc} onClick={() => chooseSort("cloud")} />
                <SortHead label={ar.colLiquidity} active={sortKey === "grade"} desc={sortDesc} onClick={() => chooseSort("grade")} />
                <SortHead label={ar.colFunds} active={sortKey === "funds"} desc={sortDesc} onClick={() => chooseSort("funds")} />
                <SortHead label={ar.colShariah} active={sortKey === "shariah"} desc={sortDesc} onClick={() => chooseSort("shariah")} />
                <SortHead label={ar.colHealth} active={sortKey === "health"} desc={sortDesc} onClick={() => chooseSort("health")} />
                <SortHead label={ar.colAnalysts} active={sortKey === "analysts"} desc={sortDesc} onClick={() => chooseSort("analysts")} />
              </tr>
            </thead>
            <tbody>
              {visible.map((row) => {
                const lamp = lamps.get(row.symbol);
                const change = row.change;
                return (
                  <tr
                    key={row.symbol}
                    className="cursor-pointer border-t border-white/5 hover:bg-white/[0.04]"
                    onClick={() => onOpen({ symbol: row.symbol, name: row.name })}
                  >
                    <td className="px-3 py-2">
                      <div className="flex items-center gap-2">
                        <CorrectionLamp kind={lamp} />
                        <div>
                          <div className="font-bold text-zinc-100">{row.name}</div>
                          <div className="text-xs text-zinc-500">{row.symbol}</div>
                        </div>
                      </div>
                    </td>
                    <td className="px-3 py-2 tabular-nums">{formatPrice(row.price)}</td>
                    <td
                      className={`px-3 py-2 tabular-nums ${
                        change != null && change > 0 ? "text-emerald-300" : change != null && change < 0 ? "text-rose-300" : ""
                      }`}
                    >
                      {formatPercent(change, 2)}
                    </td>
                    <td className="px-3 py-2">{pathLabel(row.path)}</td>
                    <td className="px-3 py-2">{cloudLabel(row)}</td>
                    <td className="px-3 py-2">
                      <div>{gradeLabel(grades.get(row.symbol))}</div>
                      <div className="text-xs tabular-nums text-zinc-400">{row.netFlow == null ? "—" : formatMoney(row.netFlow)}</div>
                    </td>
                    <td className="px-3 py-2">
                      <FundsBadge row={row} />
                    </td>
                    <td
                      className={`px-3 py-2 ${
                        shariahStatus(row.symbol) === "PURE"
                          ? "text-emerald-300"
                          : shariahStatus(row.symbol) === "MIXED"
                            ? "text-amber-200"
                            : "text-zinc-400"
                      }`}
                    >
                      {shariahLabel(row.symbol)}
                    </td>
                    <td className="px-3 py-2">{healthLabel(health.get(row.symbol), row.vwap)}</td>
                    <td className="px-3 py-2">{analystLabel(analysts.get(row.symbol))}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function SortHead({
  label,
  active,
  desc,
  onClick,
}: {
  label: string;
  active: boolean;
  desc: boolean;
  onClick: () => void;
}) {
  return (
    <th className="px-3 py-3 font-semibold">
      <button type="button" onClick={onClick} className={active ? "text-white" : "hover:text-zinc-200"}>
        {label}
        {active ? (desc ? " ↓" : " ↑") : ""}
      </button>
    </th>
  );
}

function InfluentialNews({
  live,
  onOpen,
}: {
  live: boolean;
  onOpen: (company: { symbol: string; name: string }) => void;
}) {
  const [positive, setPositive] = useState<NewsItem[]>([]);
  const [negative, setNegative] = useState<NewsItem[]>([]);
  useEffect(() => {
    if (!live) return;
    let active = true;
    const pull = () => {
      apiFetch("/api/v1/market/news", { timeoutMs: 12_000 })
        .then(async (response) => {
          if (!response.ok) return null;
          return (await response.json()) as { positive?: NewsItem[]; negative?: NewsItem[] };
        })
        .then((payload) => {
          if (!active || !payload) return;
          setPositive(Array.isArray(payload.positive) ? payload.positive : []);
          setNegative(Array.isArray(payload.negative) ? payload.negative : []);
        })
        .catch(() => undefined);
    };
    pull();
    const timer = window.setInterval(pull, 10 * 60_000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [live]);
  return (
    <section className="space-y-3 rounded-2xl border border-white/10 bg-zinc-950/40 p-4 text-right">
      <h2 className="text-base font-black text-zinc-50">{ar.newsTitle}</h2>
      {positive.length + negative.length === 0 ? (
        <p className="text-sm text-zinc-500">{ar.newsEmpty}</p>
      ) : (
        <div className="grid gap-3 lg:grid-cols-2">
          <NewsList title={ar.newsPositive} rows={positive} tone="text-emerald-200" onOpen={onOpen} />
          <NewsList title={ar.newsNegative} rows={negative} tone="text-rose-200" onOpen={onOpen} />
        </div>
      )}
    </section>
  );
}

function NewsList({
  title,
  rows,
  tone,
  onOpen,
}: {
  title: string;
  rows: NewsItem[];
  tone: string;
  onOpen: (company: { symbol: string; name: string }) => void;
}) {
  return (
    <div className="space-y-2">
      <h3 className={`text-sm font-bold ${tone}`}>{title}</h3>
      {rows.length === 0 ? <p className="text-xs text-zinc-500">{ar.newsEmpty}</p> : null}
      {rows.map((row) => (
        <article key={`${row.url}-${row.title}`} className="rounded-xl border border-white/10 px-3 py-2">
          <a href={row.url} target="_blank" rel="noreferrer" className="text-sm font-semibold text-zinc-100 hover:text-white">
            {row.title}
          </a>
          <p className="mt-1 text-[11px] text-zinc-500">
            {row.source}
            {row.published_at ? ` · ${row.published_at.slice(0, 16).replace("T", " ")}` : ""}
          </p>
          <div className="mt-2 flex flex-wrap gap-1">
            {(row.companies || []).map((company) => (
              <button
                key={company.symbol}
                type="button"
                onClick={() => onOpen(company)}
                className="rounded-full border border-white/15 px-2 py-0.5 text-[11px] font-bold text-zinc-200"
              >
                {company.name} {company.symbol}
              </button>
            ))}
          </div>
        </article>
      ))}
    </div>
  );
}

function ResilientNames({
  rows,
  indexChange,
  onOpen,
}: {
  rows: DigitalTapeRow[];
  indexChange: number | null;
  onOpen: (company: { symbol: string; name: string }) => void;
}) {
  const measured = rows.filter((row) => row.change != null);
  const falling = measured.filter((row) => (row.change ?? 0) < 0).length;
  const broadDecline = measured.length >= 8 && falling > measured.length / 2;
  const indexDown = indexChange != null && indexChange < 0;
  const weak = indexDown || broadDecline;
  const steady = weak
    ? measured.filter((row) => (row.change ?? 0) >= 0).sort((left, right) => (right.change ?? 0) - (left.change ?? 0)).slice(0, 12)
    : [];
  return (
    <section className="space-y-2 rounded-2xl border border-white/10 bg-zinc-950/40 p-4 text-right">
      <h2 className="text-base font-black text-zinc-50">{ar.resilientTitle}</h2>
      {!weak ? <p className="text-sm text-zinc-500">{ar.resilientEmpty}</p> : null}
      {weak && steady.length === 0 ? <p className="text-sm text-zinc-500">{ar.resilientNone}</p> : null}
      {steady.length ? (
        <div className="flex flex-wrap gap-2">
          {steady.map((row) => (
            <button
              key={row.symbol}
              type="button"
              onClick={() => onOpen({ symbol: row.symbol, name: row.name })}
              className="rounded-xl border border-emerald-400/30 bg-emerald-500/10 px-3 py-2 text-right"
            >
              <span className="block text-sm font-bold text-zinc-50">{row.name}</span>
              <span className="text-[11px] text-zinc-400">{row.symbol}</span>
              <span className="ms-2 font-mono text-xs text-emerald-200" dir="ltr">
                {formatPrice(row.price)} {formatPercent(row.change, 2)}
              </span>
            </button>
          ))}
        </div>
      ) : null}
    </section>
  );
}

function filterCount(
  id: FilterId,
  rows: DigitalTapeRow[],
  shariah: ShariahFilter,
  query: string,
  opportunities: Set<string>,
  analysts: Map<string, AnalystPickRow>,
): number {
  const needle = query.trim().toLowerCase();
  return rows.filter((row) => {
    if (!passesShariahFilter(row.symbol, shariah)) return false;
    if (needle && !row.symbol.includes(needle) && !row.name.toLowerCase().includes(needle)) return false;
    if (id === "pure") return passesShariahFilter(row.symbol, "pure");
    if (id === "opportunities") return opportunities.has(row.symbol);
    if (id === "consensus") return analysts.has(row.symbol);
    return true;
  }).length;
}

function FundsBadge({ row }: { row: DigitalTapeRow }) {
  const text = fundsLabel(row);
  if (text === "—") return <>—</>;
  const hot = row.blockSide === "buy" || row.signal === "entry" || (row.blocks ?? 0) > 0;
  return (
    <span
      className={`inline-flex rounded-full border px-2 py-0.5 text-[11px] font-bold ${
        hot ? "border-emerald-400/40 bg-emerald-500/15 text-emerald-100" : "border-white/10 text-zinc-200"
      }`}
    >
      {text}
    </span>
  );
}

function CorrectionLamp({ kind }: { kind: "approach" | "rebound" | undefined }) {
  if (kind === "approach") {
    return (
      <span className="relative inline-flex h-3.5 w-3.5" title={ar.colCorrection} aria-label={ar.colCorrection}>
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-amber-500 opacity-75" />
        <span className="relative inline-flex h-3.5 w-3.5 animate-pulse rounded-full bg-amber-500 shadow-[0_0_12px_3px_rgba(245,158,11,0.95)]" />
      </span>
    );
  }
  if (kind === "rebound") {
    return <span className="inline-flex h-3.5 w-3.5 rounded-full bg-emerald-400" aria-hidden="true" />;
  }
  return null;
}
