"use client";

import { useEffect, useRef, useState, type AnimationEvent, type ReactNode } from "react";

import { ar } from "@/lib/ar";
import { formatPercent, formatPrice } from "@/lib/liquidity";
import type { MarketAlert } from "@/lib/notifications";
import { fetchTickChartMarket, type TickChartQuote } from "@/lib/tickchartStatus";

function tapeDuration(count: number): string {
  return `${Math.max(2400, count * 30)}s`;
}

export function PriceTicker({ alerts = [] }: { alerts?: MarketAlert[] }) {
  const [quotes, setQuotes] = useState<TickChartQuote[]>([]);
  const [today, setToday] = useState("");
  const pending = useRef<TickChartQuote[]>([]);

  useEffect(() => {
    setToday(new Date().toLocaleDateString("ar-SA"));
  }, []);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      const next = await fetchTickChartMarket();
      if (!alive || !next.length) return;
      pending.current = next;
      setQuotes((current) => (current.length ? current : next));
    };
    void load();
    const timer = window.setInterval(() => {
      void load();
    }, quotes.length ? 45_000 : 8_000);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, [quotes.length]);

  const onPriceLoop = (event: AnimationEvent<HTMLDivElement>) => {
    if (event.animationName !== "ticker") return;
    if (pending.current.length) setQuotes(pending.current);
  };

  return (
    <div className="group/ticker fixed inset-x-0 top-0 z-40 border-b border-zinc-800 bg-zinc-950/95 text-xs text-zinc-300" dir="rtl">
      <TapeRow label={ar.priceTickerLabel} trailing={today}>
        {quotes.length ? (
          <div
            dir="ltr"
            onAnimationIteration={onPriceLoop}
            className="flex w-max animate-ticker items-center gap-8 whitespace-nowrap group-hover/ticker:[animation-play-state:paused] motion-reduce:animate-none"
            style={{ animationDuration: tapeDuration(quotes.length) }}
          >
            <TickerQuotes quotes={quotes} prefix="a" />
            <TickerQuotes quotes={quotes} prefix="b" />
          </div>
        ) : (
          <p className="truncate text-zinc-500">{ar.priceTickerEmpty}</p>
        )}
      </TapeRow>
      <TapeRow label={ar.notifyTicker}>
        {alerts.length ? (
          <div
            dir="ltr"
            className="flex w-max animate-ticker items-center gap-8 whitespace-nowrap group-hover/ticker:[animation-play-state:paused] motion-reduce:animate-none"
            style={{ animationDuration: tapeDuration(alerts.length) }}
          >
            <AlertQuotes alerts={alerts} prefix="a" />
            <AlertQuotes alerts={alerts} prefix="b" />
          </div>
        ) : (
          <p className="truncate text-zinc-500">{ar.notifyEmpty}</p>
        )}
      </TapeRow>
    </div>
  );
}

function TapeRow({
  label,
  trailing,
  children,
}: {
  label: string;
  trailing?: string;
  children: ReactNode;
}) {
  return (
    <div className="flex items-center justify-between gap-3 overflow-hidden border-b border-zinc-800/80 px-4 py-1.5 pl-14 last:border-b-0 sm:pl-4">
      <div className="flex shrink-0 items-center gap-2 whitespace-nowrap font-semibold text-sky-400">
        <span className="h-2 w-2 animate-ping rounded-full bg-sky-400" />
        {label}
      </div>
      <div className="min-w-0 flex-1 overflow-hidden">{children}</div>
      {trailing ? <div className="shrink-0 whitespace-nowrap font-mono text-[11px] text-zinc-400">{trailing}</div> : null}
    </div>
  );
}

function TickerQuotes({ quotes, prefix }: { quotes: TickChartQuote[]; prefix: string }) {
  return quotes.map((row) => {
    const change = row.price_change_pct;
    const tone = change > 0 ? "text-emerald-400" : change < 0 ? "text-rose-400" : "text-zinc-300";
    return (
      <span key={`${prefix}-${row.symbol}`} className={`inline-flex items-center gap-2 ${tone}`}>
        <span className="text-zinc-200">{row.name}</span>
        <span className="font-mono text-zinc-400">{row.symbol}</span>
        <span className="font-mono">{formatPrice(row.last_price)}</span>
        <span className="font-mono">{formatPercent(change)}</span>
      </span>
    );
  });
}

function AlertQuotes({ alerts, prefix }: { alerts: MarketAlert[]; prefix: string }) {
  return alerts.map((item) => (
    <span key={`${prefix}-${item.id}`} className="inline-flex items-center gap-2 text-zinc-200">
      <span>⚡</span>
      <span className="font-semibold text-sky-300">{item.title}</span>
      <span>{item.message}</span>
    </span>
  ));
}

export default PriceTicker;
