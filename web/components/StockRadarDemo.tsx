"use client";

import { useState } from "react";
import Link from "next/link";

import { RizgLogo } from "@/components/RizgLogo";
import { StockRadarView } from "@/components/StockRadarView";
import { ar } from "@/lib/ar";

export function StockRadarDemo() {
  const [selectedSymbol, setSelectedSymbol] = useState<string>();

  return (
    <section className="mx-auto flex w-full max-w-7xl flex-col gap-5 px-4 py-6 sm:px-6 lg:px-8">
      <header className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <RizgLogo iconClassName="h-12 w-12 sm:h-14 sm:w-14" />
          <h1 className="mt-2 text-3xl font-semibold tracking-tight text-zinc-50">{ar.radarDemoTitle}</h1>
          <p className="mt-2 max-w-2xl text-sm leading-relaxed text-zinc-500">{ar.radarDemoHint}</p>
        </div>
        <Link
          href="/"
          className="rounded-full border border-zinc-700 px-3 py-2 text-xs text-zinc-300 hover:border-emerald-500"
        >
          {ar.radarBack}
        </Link>
      </header>

      <StockRadarView selectedSymbol={selectedSymbol} onSelect={setSelectedSymbol} />
    </section>
  );
}
