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
  const pure = value === "pure";
  return (
    <button
      type="button"
      role="switch"
      aria-checked={pure}
      aria-label={ar.shariahToggle}
      title={pure ? ar.shariahFilterPureHint : ar.shariahFilterAllHint}
      onClick={() => onChange(pure ? "all" : "pure")}
      className={`inline-flex min-h-11 items-center gap-3 rounded-full border px-3 py-1.5 text-sm font-bold transition ${
        pure
          ? "border-emerald-400/50 bg-emerald-500/20 text-emerald-50 shadow-[0_0_18px_rgba(16,185,129,0.18)]"
          : "border-zinc-700 bg-zinc-950 text-zinc-300 hover:border-emerald-500/30 hover:text-zinc-100"
      }`}
    >
      <span
        aria-hidden="true"
        dir="ltr"
        className={`relative h-6 w-11 shrink-0 rounded-full transition ${pure ? "bg-emerald-500" : "bg-zinc-700"}`}
      >
        <span
          className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-all ${pure ? "left-5" : "left-0.5"}`}
        />
      </span>
      <span className="text-start leading-tight">
        {ar.shariahToggle}
        <span className="mt-0.5 block text-[10px] font-medium text-zinc-400">
          {pure ? ar.shariahFilterPureHint : ar.shariahFilterAllHint}
        </span>
      </span>
    </button>
  );
}
