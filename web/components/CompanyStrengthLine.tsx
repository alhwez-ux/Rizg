"use client";

import { useEffect, useState } from "react";

import { ar } from "@/lib/ar";
import { companyRankFor, strengthTone } from "@/lib/rankingMatrix";

export function CompanyStrengthLine({ symbol }: { symbol: string }) {
  const [category, setCategory] = useState<string | null | undefined>(undefined);

  useEffect(() => {
    let alive = true;
    setCategory(undefined);
    companyRankFor(symbol)
      .then((rank) => {
        if (alive) setCategory(rank?.category ?? null);
      })
      .catch(() => {
        if (alive) setCategory(null);
      });
    return () => {
      alive = false;
    };
  }, [symbol]);

  if (category === undefined) return null;
  const tone = category ? strengthTone(category) : "mid";
  const toneClass =
    tone === "strong"
      ? "border-emerald-400/40 bg-emerald-500/10 text-emerald-200"
      : tone === "steady"
        ? "border-sky-400/40 bg-sky-500/10 text-sky-200"
        : tone === "weak"
          ? "border-amber-400/40 bg-amber-500/10 text-amber-200"
          : tone === "risk"
            ? "border-rose-400/40 bg-rose-500/10 text-rose-200"
            : "border-zinc-700 bg-zinc-900 text-zinc-400";

  return (
    <p className={`mx-auto mt-2 inline-flex max-w-full rounded-full border px-3 py-1 text-[11px] font-semibold sm:mx-0 ${toneClass}`}>
      {category ? `${ar.followStrength}: ${category}` : ar.followStrengthMissing}
    </p>
  );
}
