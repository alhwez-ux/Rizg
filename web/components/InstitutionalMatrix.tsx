"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { useScreener } from "@/hooks/useScreener";
import { ar } from "@/lib/ar";
import { holdDisplayedRows, nextDisplayWake, RADAR_DISPLAY_MS, type HeldRow } from "@/lib/radarHold";
import {
  accumulationBoard,
  distributionBoard,
  entryBoard,
  exitBoard,
  type BoardCard,
} from "@/lib/institutionalMatrix";
import { DataSkeleton } from "@/components/DataSkeleton";
import { formatPrice } from "@/lib/liquidity";
import { displayCompanyTitle } from "@/lib/listedCompanies";
import type { ShariahFilter } from "@/lib/shariah";
import type { SmartMoneyRow } from "@/lib/smartMoney";

const COLUMN_CAP = 8;

export function InstitutionalMatrix({
  shariahFilter,
  funds,
  fundsLoading,
  showEntry,
  showExit,
  showAccumulation,
  showDistribution,
  onOpen,
}: {
  shariahFilter: ShariahFilter;
  funds: SmartMoneyRow[];
  fundsLoading: boolean;
  showEntry: boolean;
  showExit: boolean;
  showAccumulation: boolean;
  showDistribution: boolean;
  onOpen: (company: { symbol: string; name: string }) => void;
}) {
  const { snapshot, error } = useScreener();
  const rows = useMemo(() => {
    const merged = [...(snapshot?.watchlist ?? []), ...(snapshot?.radar ?? [])];
    const seen = new Set<string>();
    return merged.filter((row) => {
      if (!row.symbol || seen.has(row.symbol)) return false;
      seen.add(row.symbol);
      return true;
    });
  }, [snapshot]);

  const entry = useHeldBoard(showEntry ? entryBoard(rows, shariahFilter) : []);
  const exit = useHeldBoard(showExit ? exitBoard(rows, shariahFilter) : []);
  const accumulation = useHeldBoard(showAccumulation ? accumulationBoard(funds, shariahFilter) : []);
  const distribution = useHeldBoard(showDistribution ? distributionBoard(funds, shariahFilter) : []);
  const waiting = !snapshot && !error;

  const columns = [
    showEntry
      ? { id: "entry", title: ar.matrixEntry, tone: "emerald", rows: entry, empty: ar.matrixEmptyEntry }
      : null,
    showExit ? { id: "exit", title: ar.matrixExit, tone: "rose", rows: exit, empty: ar.matrixEmptyExit } : null,
    showAccumulation
      ? {
          id: "accumulation",
          title: ar.matrixAccumulation,
          tone: "sky",
          rows: accumulation,
          empty: ar.matrixEmptyAccumulation,
        }
      : null,
    showDistribution
      ? {
          id: "distribution",
          title: ar.matrixDistribution,
          tone: "amber",
          rows: distribution,
          empty: ar.matrixEmptyDistribution,
        }
      : null,
  ].filter((column): column is NonNullable<typeof column> => column != null);

  if (columns.length === 0) return null;

  const settled = Boolean(snapshot) && !fundsLoading;
  const allEmpty = columns.every((column) => column.rows.length === 0);
  if (settled && allEmpty) {
    return (
      <section className="rounded-xl border border-zinc-800/80 bg-zinc-950/40 px-4 py-2 text-center">
        <p className="text-sm font-bold text-zinc-300">{ar.matrixTitle}</p>
        <p className="text-[11px] text-zinc-500">{error ? ar.radarLoadError : ar.matrixEmptyAll}</p>
      </section>
    );
  }

  return (
    <section className="space-y-3 text-start">
      <div className="text-center">
        <h2 className="text-lg font-bold text-zinc-100">{ar.matrixTitle}</h2>
        <p className="mt-1 text-xs text-zinc-400">{ar.matrixHint}</p>
      </div>
      {error ? <p className="text-center text-xs text-rose-300">{ar.radarLoadError}</p> : null}
      <div className={`grid items-start gap-3 ${columns.length > 1 ? "md:grid-cols-2 xl:grid-cols-4" : ""}`}>
        {columns.map((column) => (
          <section
            key={column.id}
            className={`flex flex-col rounded-2xl border p-3 ${column.rows.length === 0 ? "" : "min-h-48"} ${toneClass(column.tone)}`}
          >
            <header className={`flex items-center justify-between gap-2 ${column.rows.length === 0 ? "mb-1" : "mb-3"}`}>
              <h3 className="text-sm font-black">{column.title}</h3>
              <span className="font-mono text-xs opacity-70">{column.rows.length}</span>
            </header>
            {waiting || (fundsLoading && (column.id === "accumulation" || column.id === "distribution") && column.rows.length === 0) ? (
              <DataSkeleton kind="grid" rows={2} />
            ) : column.rows.length === 0 ? (
              <p className="px-1 py-2 text-center text-xs text-zinc-500">{column.empty}</p>
            ) : (
              <ul className="max-h-[28rem] space-y-2 overflow-y-auto">
                {column.rows.map((card) => (
                  <li key={card.symbol}>
                    <button
                      type="button"
                      onClick={() => onOpen({ symbol: card.symbol, name: card.name })}
                      className="w-full rounded-xl border border-white/5 bg-zinc-950/50 px-3 py-2.5 text-start transition hover:border-white/15 hover:bg-zinc-950/80"
                    >
                      <span className="flex items-baseline justify-between gap-2">
                        <span className="truncate text-sm font-bold text-zinc-50">
                          {displayCompanyTitle(card.symbol, card.name)}
                        </span>
                        <span className="shrink-0 font-mono text-xs text-zinc-400" dir="ltr">
                          {card.symbol}
                        </span>
                      </span>
                      <span className="mt-1 flex items-baseline justify-between gap-2 text-xs">
                        <span className="font-mono text-zinc-200" dir="ltr">
                          {formatPrice(card.price)}
                        </span>
                        <span className="font-mono text-zinc-400" dir="ltr">
                          {card.metric}
                        </span>
                      </span>
                      <span className="mt-1 line-clamp-2 block text-[11px] leading-4 text-zinc-500">{card.reason}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>
        ))}
      </div>
    </section>
  );
}

function useHeldBoard(incoming: BoardCard[]): BoardCard[] {
  const heldRef = useRef<HeldRow<BoardCard>[]>([]);
  const [tick, setTick] = useState(0);
  const shown = useMemo(() => {
    const next = holdDisplayedRows(heldRef.current, incoming, Date.now(), RADAR_DISPLAY_MS, COLUMN_CAP);
    heldRef.current = next;
    return next.map((item) => item.row);
  }, [incoming, tick]);

  useEffect(() => {
    const wait = nextDisplayWake(heldRef.current, Date.now());
    if (wait == null) return;
    const timer = window.setTimeout(() => setTick((value) => value + 1), Math.max(wait, 0) + 30);
    return () => window.clearTimeout(timer);
  }, [shown]);

  return shown;
}

function toneClass(tone: string): string {
  if (tone === "emerald") return "border-emerald-500/30 bg-emerald-950/20 text-emerald-100";
  if (tone === "rose") return "border-rose-500/30 bg-rose-950/20 text-rose-100";
  if (tone === "sky") return "border-sky-500/30 bg-sky-950/20 text-sky-100";
  return "border-amber-500/30 bg-amber-950/20 text-amber-100";
}
