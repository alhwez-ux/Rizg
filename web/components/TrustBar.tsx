"use client";

import { useEffect, useState } from "react";

import { useConnectionGuard } from "@/hooks/useConnectionGuard";
import { ar } from "@/lib/ar";
import { formatRelativeAgo } from "@/lib/relativeTime";
import { fetchTickChartStatus } from "@/lib/tickchartStatus";

export function TrustBar() {
  return (
    <footer className="fixed inset-x-0 bottom-0 z-40 border-t border-zinc-800/90 bg-zinc-950/95 px-3 pb-[max(0.5rem,env(safe-area-inset-bottom))] pt-2 backdrop-blur-md">
      <LiveDataStatus />
      <p className="mt-1 text-center text-[11px] leading-5 text-zinc-400">{ar.disclaimer}</p>
    </footer>
  );
}

function LiveDataStatus() {
  const { apiUp } = useConnectionGuard();
  const [syncAt, setSyncAt] = useState<number | null>(null);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      const status = await fetchTickChartStatus();
      if (!alive) return;
      const stamp = status?.last_sync_at ? Date.parse(status.last_sync_at) : Number.NaN;
      if (Number.isFinite(stamp)) setSyncAt(stamp);
    };
    void load();
    const timer = window.setInterval(() => {
      void load();
    }, 5_000);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, []);

  const tone = apiUp == null ? "checking" : apiUp ? "up" : "down";
  const dot = tone === "up" ? "var(--rizg-gain)" : tone === "down" ? "var(--rizg-loss)" : "#d4a017";
  const label = tone === "up" ? ar.apiStatusUp : tone === "down" ? ar.apiStatusDown : ar.apiStatusChecking;
  const when = syncAt == null ? ar.lastUpdateWaiting : `${ar.lastUpdate}: ${formatRelativeAgo(now - syncAt)}`;

  return (
    <div className="flex flex-wrap items-center justify-center gap-x-3 gap-y-1 text-[11px]">
      <span className="inline-flex items-center gap-1.5 font-semibold text-zinc-200">
        <span className="h-2.5 w-2.5 rounded-full" style={{ background: dot }} aria-hidden="true" />
        <span className="sr-only">{ar.apiStatusLabel}</span>
        {label}
      </span>
      <span className="text-zinc-400">{when}</span>
    </div>
  );
}
