"use client";

import { useEffect, useState } from "react";

import { ar } from "@/lib/ar";
import { fetchSchedulerStatus, type SchedulerStatus } from "@/lib/tasiScheduler";

export function TasiSchedulerChip() {
  const [status, setStatus] = useState<SchedulerStatus | null>(null);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      const next = await fetchSchedulerStatus();
      if (alive) setStatus(next);
    };
    void load();
    const timer = window.setInterval(() => {
      void load();
    }, 60_000);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, []);

  const live = Boolean(status?.running && status.enabled);
  const label = status?.phase_label || ar.schedulerHint;
  const tone = status?.intraday
    ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-400"
    : "border-zinc-700 bg-zinc-900 text-zinc-300";

  return (
    <div className={`flex items-center gap-2 rounded-xl border px-3 py-1.5 text-xs font-semibold ${tone}`} title={ar.schedulerHint}>
      <span className={`h-2 w-2 rounded-full ${live ? "animate-pulse bg-emerald-400" : "bg-zinc-500"}`} />
      {label}
    </div>
  );
}

export default TasiSchedulerChip;
