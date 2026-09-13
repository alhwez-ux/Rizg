"use client";

import { useEffect, useState } from "react";

import { ar } from "@/lib/ar";
import { fetchTickChartStatus, type TickChartStatus } from "@/lib/tickchartStatus";

export function TickChartSyncChip() {
  const [status, setStatus] = useState<TickChartStatus | null>(null);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      const next = await fetchTickChartStatus();
      if (alive) setStatus(next);
    };
    void load();
    const timer = window.setInterval(() => {
      void load();
    }, 2_000);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, []);

  const live = Boolean(status?.connected || status?.autosync_watching);
  const label = status?.last_file
    ? `${ar.tickchartSyncLive} · ${status.last_file}`
    : live
      ? ar.tickchartSyncWatching
      : ar.tickchartSyncIdle;
  const tone = live
    ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-400"
    : "border-zinc-700 bg-zinc-900 text-zinc-400";

  return (
    <div className={`flex items-center gap-2 rounded-xl border px-3 py-1.5 text-xs font-semibold ${tone}`} title={ar.tickchartSyncHint}>
      <span className={`h-2 w-2 rounded-full ${live ? "animate-pulse bg-emerald-400" : "bg-zinc-500"}`} />
      {label}
    </div>
  );
}

export default TickChartSyncChip;
