"use client";

import { ar } from "@/lib/ar";
import type { ShariahFilter } from "@/lib/shariah";

export function ShariahFilterBar({
  value,
  onChange,
}: {
  value: ShariahFilter;
  onChange: (next: ShariahFilter) => void;
}) {
  return (
    <div className="flex w-full flex-col items-center gap-2 rounded-2xl border border-emerald-500/25 bg-emerald-500/5 px-4 py-3 sm:flex-row sm:justify-between">
      <p className="text-sm font-semibold text-zinc-100">{ar.shariahFilterTitle}</p>
      <div className="flex rounded-xl border border-zinc-800 bg-zinc-950 p-1 text-sm font-bold">
        <button
          type="button"
          onClick={() => onChange("all")}
          className={`rounded-lg px-4 py-1.5 transition ${
            value === "all" ? "bg-sky-600 text-white shadow-lg shadow-sky-900/30" : "text-zinc-400 hover:text-zinc-100"
          }`}
        >
          {ar.shariahFilterAll}
        </button>
        <button
          type="button"
          onClick={() => onChange("pure")}
          className={`rounded-lg px-4 py-1.5 transition ${
            value === "pure"
              ? "bg-emerald-600 text-white shadow-lg shadow-emerald-900/30"
              : "text-zinc-400 hover:text-zinc-100"
          }`}
        >
          {ar.shariahFilterPure}
        </button>
      </div>
      <p className="text-xs text-zinc-400">{value === "pure" ? ar.shariahFilterPureHint : ar.shariahFilterAllHint}</p>
    </div>
  );
}
