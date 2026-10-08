"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { CompanyName } from "@/components/CompanyName";
import { FinancialGradeBadge } from "@/components/GradeBadge";
import { DataSkeleton } from "@/components/DataSkeleton";
import { LiquidityRadarCard } from "@/components/LiquidityRadarCard";
import { CloseRecommendationIcon } from "@/components/CloseRecommendationIcon";
import { PathBadge } from "@/components/PathBadge";
import { graduatedTargets } from "@/lib/tradeTargets";
import { useTasiSession } from "@/hooks/useTasiSession";
import { sessionPollMs } from "@/lib/sessionPoll";
import { ar } from "@/lib/ar";
import { formatPercent, formatPrice } from "@/lib/liquidity";
import {
  fetchMarketRecommendations,
  freezeRecommendationEntry,
  recommendationResolved,
  riyadhSessionDate,
  type FrozenEntry,
  type MarketRecommendation,
  type RecommendationKind,
  type RecommendationScanMode,
} from "@/lib/recommendations";
import { SESSION_REFRESHED_EVENT } from "@/lib/tickchartStatus";
import { useConnectionGuard } from "@/hooks/useConnectionGuard";
import { useTapeLastPrices } from "@/hooks/useTapeLastPrices";
import { passesShariahFilter, type ShariahFilter } from "@/lib/shariah";

type FilterKind = "all" | RecommendationKind;
type SortKey = "confidence" | "close" | "symbol";

const LIVE_POLL_MS = 12_000;
const CLOSE_POLL_MS = 45_000;

function isTimeoutError(error: unknown): boolean {
  return error instanceof Error && (error.name === "TimeoutError" || error.name === "AbortError");
}

export function RecommendationsCard({ shariahFilter = "all" }: { shariahFilter?: ShariahFilter }) {
  const [rows, setRows] = useState<MarketRecommendation[]>([]);
  const [loading, setLoading] = useState(true);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [late, setLate] = useState(false);
  const [cached, setCached] = useState(false);
  const [sessionLabel, setSessionLabel] = useState<string | null>(null);
  const [scanMode, setScanMode] = useState<RecommendationScanMode | string>("end_of_day");
  const { live: sessionLive, label: sessionPhaseLabel } = useTasiSession();
  const [filter, setFilter] = useState<FilterKind>("all");
  const [sortKey, setSortKey] = useState<SortKey>("confidence");
  const [sortDir, setSortDir] = useState<"desc" | "asc">("desc");
  const [selected, setSelected] = useState<MarketRecommendation | null>(null);
  const inflight = useRef(false);
  const slowTimer = useRef(0);
  const loadedRef = useRef(false);
  const rowsRef = useRef<MarketRecommendation[]>([]);
  const entryLocks = useRef(new Map<string, FrozenEntry>());
  const completedRef = useRef(new Set<string>());
  const sessionDateRef = useRef("");
  const { isConnected } = useConnectionGuard();
  const [resolvedTick, setResolvedTick] = useState(0);
  const symbols = useMemo(() => rows.map((row) => row.symbol), [rows]);
  const liveLast = useTapeLastPrices(symbols);

  const mergeIncoming = useCallback((data: MarketRecommendation[]) => {
    const day = riyadhSessionDate();
    if (sessionDateRef.current !== day) {
      sessionDateRef.current = day;
      entryLocks.current.clear();
      completedRef.current.clear();
    }
    const incoming = new Set(data.map((row) => row.symbol.trim().toUpperCase()).filter(Boolean));
    for (const done of [...completedRef.current]) {
      if (!incoming.has(done)) {
        completedRef.current.delete(done);
        entryLocks.current.delete(done);
      }
    }
    const merged: MarketRecommendation[] = [];
    for (const row of data) {
      const key = row.symbol.trim().toUpperCase();
      if (!key || completedRef.current.has(key) || recommendationResolved(row)) {
        if (key) completedRef.current.add(key);
        continue;
      }
      const frozen = freezeRecommendationEntry(row, entryLocks.current.get(key));
      entryLocks.current.set(key, frozen.lock);
      if (recommendationResolved(frozen.row)) {
        completedRef.current.add(key);
        continue;
      }
      merged.push(frozen.row);
    }
    return merged;
  }, []);

  const load = useCallback(async () => {
    if (inflight.current) return;
    inflight.current = true;
    if (!loadedRef.current) setLoading(true);
    setError(null);
    window.clearTimeout(slowTimer.current);
    if (rowsRef.current.length > 0) {
      slowTimer.current = window.setTimeout(() => setLate(true), 1_200);
    }
    try {
      const result = await fetchMarketRecommendations();
      const data = mergeIncoming(result.data);
      rowsRef.current = data;
      setRows(data);
      setCached(result.source === "cached" || (result.source === "fallback" && data.length > 0));
      setSessionLabel(result.session_label || null);
      setScanMode(result.scan_mode === "live" ? "live" : "end_of_day");
      loadedRef.current = true;
      setLoaded(true);
      setError(null);
      setLate(false);
      setSelected((current) => {
        if (!current) return null;
        return data.find((row) => row.symbol === current.symbol) ?? null;
      });
    } catch (err) {
      loadedRef.current = true;
      setLoaded(true);
      if (rowsRef.current.length > 0 || isTimeoutError(err)) {
        setLate(true);
      } else {
        setError(ar.recoLoadError);
      }
    } finally {
      window.clearTimeout(slowTimer.current);
      inflight.current = false;
      setLoading(false);
    }
  }, [mergeIncoming]);

  useEffect(() => {
    if (!isConnected) {
      setLoading(false);
      return;
    }
    void load();
    const onRefresh = () => {
      void load();
    };
    window.addEventListener(SESSION_REFRESHED_EVENT, onRefresh);
    return () => {
      window.removeEventListener(SESSION_REFRESHED_EVENT, onRefresh);
    };
  }, [isConnected, load]);

  useEffect(() => {
    if (!isConnected) return;
    const idle = scanMode === "live" || sessionLive ? LIVE_POLL_MS : CLOSE_POLL_MS;
    let timer = 0;
    const arm = () => {
      timer = window.setTimeout(() => {
        void load();
        arm();
      }, sessionPollMs(idle));
    };
    arm();
    return () => window.clearTimeout(timer);
  }, [isConnected, load, scanMode, sessionLive]);

  useEffect(() => {
    let changed = false;
    for (const row of rows) {
      const key = row.symbol.toUpperCase();
      const last = liveLast.get(key);
      if (!sessionLive) {
        if (recommendationResolved(row, row.close_price)) {
          if (!completedRef.current.has(key)) {
            completedRef.current.add(key);
            changed = true;
          }
        }
        continue;
      }
      if (last != null && recommendationResolved(row, last)) {
        if (!completedRef.current.has(key)) {
          completedRef.current.add(key);
          changed = true;
        }
      }
    }
    if (changed) setResolvedTick((tick) => tick + 1);
  }, [rows, liveLast, sessionLive]);

  const priced = useMemo(() => {
    const next: MarketRecommendation[] = [];
    for (const row of rows) {
      const key = row.symbol.toUpperCase();
      if (completedRef.current.has(key)) continue;
      const last = liveLast.get(key);
      const overlay =
        last == null
          ? { ...row, last_price: sessionLive ? null : row.last_price }
          : { ...row, last_price: last };
      const resolved = sessionLive
        ? overlay.last_price != null && recommendationResolved(overlay, overlay.last_price)
        : recommendationResolved(overlay, overlay.close_price);
      if (resolved) continue;
      next.push(overlay);
    }
    return next;
  }, [rows, liveLast, resolvedTick, sessionLive]);

  useEffect(() => {
    if (!selected) return;
    const stillVisible = priced.some((row) => row.symbol === selected.symbol);
    if (!stillVisible) setSelected(null);
  }, [priced, selected]);

  const visible = useMemo(() => {
    const filtered = (filter === "all" ? priced : priced.filter((row) => row.signal_kind === filter)).filter((row) =>
      passesShariahFilter(row.symbol, shariahFilter),
    );
    const copy = [...filtered];
    copy.sort((left, right) => {
      const direction = sortDir === "asc" ? 1 : -1;
      if (sortKey === "symbol") {
        return left.symbol.localeCompare(right.symbol) * direction;
      }
      if (sortKey === "close") {
        return (left.close_price - right.close_price) * direction;
      }
      return (left.confidence_score - right.confidence_score) * direction;
    });
    return copy;
  }, [filter, priced, shariahFilter, sortDir, sortKey]);

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir((current) => (current === "desc" ? "asc" : "desc"));
      return;
    }
    setSortKey(key);
    setSortDir(key === "symbol" ? "asc" : "desc");
  };

  const live = scanMode === "live" || sessionLive;
  const buttonName = live ? ar.recoButtonLive : ar.recoButtonEod;
  const title = buttonName;
  const hint = cached && !live ? ar.recoCached : live ? ar.recoHintLive : ar.recoHintEod;
  const badge = live ? ar.recoLive : sessionLabel || sessionPhaseLabel || ar.recoClosed;
  const emptyLabel = live ? ar.recoEmptyLive : ar.recoEmptyEod;
  const priceLabel = live ? ar.recoColPriceLive : ar.recoColCloseEod;
  const horizonLabel = live ? ar.recoHorizonLive : ar.recoHorizon;

  return (
    <section className="rounded-2xl border border-zinc-800/80 bg-tape-panel/90 p-5 text-zinc-100 shadow-glow sm:p-6">
      <div className="mb-5 flex flex-col items-center justify-center gap-4 border-b border-zinc-800 pb-4 text-center">
        <div>
          <h2 className={`flex items-center justify-center gap-2 text-xl font-bold ${live ? "text-sky-100" : "text-emerald-100"}`}>
            <span
              className={`inline-flex h-9 w-9 items-center justify-center rounded-xl ${
                live ? "bg-sky-500/20 text-sky-300" : "bg-emerald-100 text-emerald-800"
              }`}
            >
              {live ? <span aria-hidden="true">⚡</span> : <CloseRecommendationIcon className="h-5 w-5" />}
            </span>
            {title}
          </h2>
          <p className="mt-1 text-xs text-zinc-500">{hint}</p>
        </div>
        <div className="flex flex-wrap items-center justify-center gap-2">
          <span
            className={`rounded-xl border px-3 py-1 text-xs font-semibold ${
              live
                ? "border-sky-500/30 bg-sky-500/10 text-sky-200"
                : "border-emerald-500/20 bg-emerald-100 text-emerald-900"
            }`}
          >
            {badge}
          </span>
          <button
            type="button"
            onClick={() => {
              void load();
            }}
            disabled={loading}
            aria-busy={loading}
            aria-label={buttonName}
            className={`inline-flex items-center gap-2 rounded-xl px-5 py-2.5 text-sm font-semibold text-white shadow-lg transition disabled:opacity-50 ${
              live
                ? "bg-gradient-to-r from-sky-500 to-cyan-500 shadow-sky-900/30 hover:from-sky-400 hover:to-cyan-400"
                : "bg-gradient-to-r from-sky-600 to-teal-600 shadow-sky-900/20 hover:from-sky-500 hover:to-teal-500"
            }`}
          >
            {loading ? <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" /> : null}
            {loading ? ar.recoRefreshing : buttonName}
          </button>
        </div>
      </div>

      {loaded ? (
        <div className="mb-4 flex flex-wrap justify-center gap-2">
          {(
            [
              ["all", ar.recoFilterAll],
              ["bounce", ar.recoFilterBounce],
              ["momentum", ar.recoFilterMomentum],
            ] as const
          ).map(([id, label]) => (
            <button
              key={id}
              type="button"
              onClick={() => setFilter(id)}
              className={`rounded-full border px-3 py-1.5 text-xs font-semibold transition ${
                filter === id
                  ? "border-sky-500/40 bg-sky-500/15 text-sky-300"
                  : "border-zinc-800 bg-zinc-950 text-zinc-400 hover:text-zinc-200"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      ) : null}

      {late && visible.length > 0 ? (
        <p className="mb-3 text-center text-xs text-zinc-500">{ar.liveTicksUpdating}</p>
      ) : null}
      {loading && !loaded && visible.length === 0 ? (
        <DataSkeleton kind="table" rows={5} />
      ) : error && visible.length === 0 ? (
        <p className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">{error}</p>
      ) : visible.length === 0 ? (
        <p className="py-8 text-center text-sm text-zinc-500">{emptyLabel}</p>
      ) : !live ? (
        <CloseBoards rows={visible} selected={selected?.symbol ?? null} onSelect={setSelected} />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px] border-collapse text-start">
            <thead>
              <tr className="border-b border-zinc-800 text-xs text-zinc-500">
                <SortHeader label={ar.recoColSymbol} active={sortKey === "symbol"} onClick={() => toggleSort("symbol")} />
                <th className="p-3 font-medium">{ar.tableColCompany}</th>
                <th className="p-3 font-medium">{ar.recoColSignal}</th>
                <SortHeader label={priceLabel} active={sortKey === "close"} onClick={() => toggleSort("close")} />
                <th className="p-3 font-medium">{ar.recoColEntry}</th>
                <th className="p-3 font-medium">{ar.targets}</th>
                <th className="p-3 font-medium">{ar.stopLoss}</th>
                <SortHeader
                  label={ar.recoColConfidence}
                  active={sortKey === "confidence"}
                  onClick={() => toggleSort("confidence")}
                />
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800/60 text-sm">
              {visible.map((row) => {
                const active = selected?.symbol === row.symbol;
                return (
                  <tr
                    key={row.symbol}
                    className={`cursor-pointer transition-colors hover:bg-zinc-950/50 ${active ? "bg-sky-950/30" : ""}`}
                    tabIndex={0}
                    onClick={() => setSelected(row)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        setSelected(row);
                      }
                    }}
                  >
                    <td className="p-3 font-mono text-sky-400" dir="ltr">
                      {row.symbol}
                    </td>
                    <td className="p-3 font-semibold text-zinc-100">
                      <span className="inline-flex flex-col items-start gap-1">
                        <CompanyName symbol={row.symbol} name={row.name} align="start" />
                        <FinancialGradeBadge symbol={row.symbol} />
                      </span>
                    </td>
                    <td className="p-3">
                      <PathBadge price={row.last_price ?? row.close_price} vwap={row.session_vwap} change={row.change_percent} />
                      <span
                        className={`rounded-xl border px-2 py-1 text-[11px] font-semibold ${
                          row.signal_kind === "bounce"
                            ? "border-amber-500/20 bg-amber-500/10 text-amber-300"
                            : "border-emerald-500/20 bg-emerald-500/10 text-emerald-300"
                        }`}
                      >
                        {row.signal_type}
                      </span>
                      {row.entry ? (
                        <span className="ms-2 rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-semibold text-emerald-800">
                          {ar.recoEntryMet}
                        </span>
                      ) : null}
                      <span className="ms-2 rounded-full border border-zinc-700 px-2 py-0.5 text-[10px] text-zinc-400">
                        {horizonLabel}
                      </span>
                    </td>
                    <td className="p-3 font-bold" dir="ltr">
                      {formatPrice(sessionLive ? (row.last_price ?? null) : row.close_price)}
                    </td>
                    <td className="p-3 text-zinc-200" dir="ltr">
                      {row.entry_price}
                    </td>
                    <td className="p-3 font-semibold text-emerald-300" dir="ltr">
                      <TargetLadder entry={row.entry_price} stop={row.stop_loss} />
                    </td>
                    <td className="p-3 font-semibold text-rose-400" dir="ltr">
                      {row.stop_loss}
                    </td>
                    <td className="p-3 font-bold text-sky-300">{row.confidence}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {selected ? (
        <div className="mt-5 space-y-4 border-t border-zinc-800 pt-5">
          <div className="rounded-xl border border-zinc-800 bg-zinc-950/50 p-4 text-xs text-zinc-400">
            <strong className="mb-1 block text-zinc-200">{ar.recoReason}</strong>
            {selected.reason}
          </div>
          <LiquidityRadarCard symbol={selected.symbol} symbolName={selected.name} />
        </div>
      ) : null}
    </section>
  );
}

function TargetLadder({ entry, stop }: { entry: string; stop: string }) {
  const plan = graduatedTargets(entry, stop);
  if (!plan) return <span>—</span>;
  return (
    <span className="inline-flex flex-col gap-0.5 text-xs">
      <span className="whitespace-nowrap">
        <span className="font-normal text-zinc-500">{ar.target1}</span> {plan.t1.toFixed(2)}
      </span>
      <span className="whitespace-nowrap">
        <span className="font-normal text-zinc-500">{ar.target2}</span> {plan.t2.toFixed(2)}
      </span>
      <span className="whitespace-nowrap">
        <span className="font-normal text-zinc-500">{ar.target3}</span> {plan.t3.toFixed(2)}
      </span>
    </span>
  );
}

function CloseBoards({
  rows,
  selected,
  onSelect,
}: {
  rows: MarketRecommendation[];
  selected: string | null;
  onSelect: (row: MarketRecommendation) => void;
}) {
  const accumulation = rows.filter((row) => row.signal_type === "الأكثر تجميعاً" || row.signal_kind === "bounce");
  const liquidity = rows.filter((row) => !accumulation.includes(row));
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <CloseBoard title="الأكثر تجميعاً" rows={accumulation} tone="border-emerald-500/25 bg-emerald-500/5" selected={selected} onSelect={onSelect} />
      <CloseBoard title="الأكثر سيولة عند الإغلاق" rows={liquidity} tone="border-amber-500/25 bg-amber-500/5" selected={selected} onSelect={onSelect} />
    </div>
  );
}

function CloseBoard({
  title,
  rows,
  tone,
  selected,
  onSelect,
}: {
  title: string;
  rows: MarketRecommendation[];
  tone: string;
  selected: string | null;
  onSelect: (row: MarketRecommendation) => void;
}) {
  return (
    <div className={`rounded-2xl border p-3 text-start ${tone}`}>
      <div className="mb-3 flex min-h-8 items-center justify-between gap-2">
        <h3 className="text-sm font-bold text-zinc-50">{title}</h3>
        <span className="rounded-full bg-zinc-950/70 px-2 py-0.5 font-mono text-xs tabular-nums text-zinc-300">{rows.length}</span>
      </div>
      {rows.length === 0 ? (
        <p className="rounded-xl border border-dashed border-zinc-800 px-3 py-8 text-center text-xs text-zinc-500">لا توجد أسماء في هذا الجانب</p>
      ) : (
        <div className="grid gap-3">
          {rows.map((row) => (
            <button
              key={row.symbol}
              type="button"
              onClick={() => onSelect(row)}
              className={`w-full rounded-2xl border bg-zinc-950/50 p-4 text-center transition hover:border-emerald-400/40 ${
                selected === row.symbol ? "border-emerald-400/50" : "border-zinc-800"
              }`}
            >
              <span className="inline-flex flex-col items-center gap-1">
                <CompanyName symbol={row.symbol} name={row.name} />
                <FinancialGradeBadge symbol={row.symbol} />
              </span>
              <div className="mt-3 flex flex-wrap items-center justify-center gap-2">
                <span className="rounded-xl border border-zinc-700 px-2.5 py-1 text-[11px] font-semibold text-zinc-200">{row.signal_type}</span>
                <PathBadge price={row.last_price ?? row.close_price} vwap={row.session_vwap} change={row.change_percent} />
              </div>
              <p className="mt-3 font-mono text-lg font-semibold text-zinc-50" dir="ltr">
                {formatPrice(row.close_price)}
                {row.change_percent ? (
                  <span className={`ms-2 text-sm ${row.change_percent > 0 ? "text-emerald-300" : "text-rose-300"}`}>
                    {formatPercent(row.change_percent)}
                  </span>
                ) : null}
              </p>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function SortHeader({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <th className="p-3 font-medium">
      <button type="button" onClick={onClick} className={`hover:text-zinc-200 ${active ? "text-sky-400" : ""}`}>
        {label}
      </button>
    </th>
  );
}

export default RecommendationsCard;
