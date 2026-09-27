"use client";

import { useEffect, useState } from "react";

import { observeSymbol, peekRegime, type FlowObservation } from "@/lib/flowIntent";
import type { TapeRegime } from "@/lib/liquidity";

export function useSymbolRegime(
  symbol: string,
  sample: Omit<FlowObservation, "at"> | null,
): TapeRegime {
  const [regime, setRegime] = useState<TapeRegime>("neutral");
  const net = sample?.netFlow;
  const buy = sample?.buyVolume;
  const sell = sample?.sellVolume;
  const price = sample?.price;

  useEffect(() => {
    setRegime(peekRegime(symbol));
  }, [symbol]);

  useEffect(() => {
    if (!symbol || net == null || !Number.isFinite(net)) return;
    const next = observeSymbol(symbol, {
      at: Date.now(),
      netFlow: net,
      buyVolume: buy,
      sellVolume: sell,
      price,
    });
    setRegime((current) => (current === next ? current : next));
  }, [buy, net, price, sell, symbol]);

  return regime;
}
