"use client";

import { useEffect, useRef, useState, type AnimationEvent } from "react";

import { ar } from "@/lib/ar";
import { formatPercent, formatPrice } from "@/lib/liquidity";
import { fetchTickChartMarket, type TickChartQuote } from "@/lib/tickchartStatus";

export function PriceTicker() {
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
    }, 45_000);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, []);

  const onLoop = (event: AnimationEvent<HTMLDivElement>) => {
    if (event.animationName !== "ticker") return;
    if (pending.current.length) setQuotes(pending.current);
  };

  return (
    <div
      className="group/ticker fixed inset-x-0 top-0 z-40 border-b border-zinc-800 bg-zinc-950/90 text-xs text-zinc-300"
      dir="rtl"
    >
      <div className="flex items-center justify-between gap-3 overflow-hidden px-4 py-2">
        <div className="flex shrink-0 items-center gap-2 whitespace-nowrap font-semibold text-sky-400">
          <span className="h-2 w-2 animate-ping rounded-full bg-sky-400" />
          {ar.notifyTicker}
        </div>
        <div className="min-w-0 flex-1 overflow-hidden">
          {quotes.length ? (
            <div
              dir="ltr"
              onAnimationIteration={onLoop}
              className="flex w-max animate-ticker items-center gap-8 whitespace-nowrap group-hover/ticker:[animation-play-state:paused] motion-reduce:animate-none"
            >
              <TickerQuotes quotes={quotes} prefix="a" />
              <TickerQuotes quotes={quotes} prefix="b" />
            </div>
          ) : (
            <p className="truncate text-zinc-500">{ar.priceTickerEmpty}</p>
          )}
        </div>
        {today ? <div className="shrink-0 whitespace-nowrap font-mono text-[11px] text-zinc-400">{today}</div> : null}
      </div>
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

export default PriceTicker;
