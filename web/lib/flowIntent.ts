import type { TapeRegime } from "@/lib/liquidity";

/** Five-minute rolling window for VWAP and block-trade confirmation. */
export const FLOW_WINDOW_MS = 300_000;
/** A side is shown only after the tape has covered the full five minutes. */
export const FLOW_MIN_SPAN_MS = 300_000;
/** |block score| must clear this before تجميع or تصريف is treated as real. */
export const REGIME_ENTER = 0.3;
/** A shown side stays up at least this long before it may switch. */
export const REGIME_DWELL_MS = 45_000;
/** A print below this notional is not an institutional block. */
export const BLOCK_NOTIONAL = 100_000;
const DUST_NOTIONAL = 1;

export interface FlowObservation {
  at: number;
  netFlow: number;
  buyVolume?: number;
  sellVolume?: number;
  price?: number | null;
}

interface FlowSample {
  at: number;
  side: 1 | -1;
  price: number;
  volume: number;
  blockNotional: number;
}

export interface FlowIntentState {
  samples: FlowSample[];
  regime: TapeRegime;
  labeledAt: number;
  lastNet: number | null;
  lastPrice: number | null;
  lastVolume: number | null;
}

const tracks = new Map<string, FlowIntentState>();

export function createFlowIntent(): FlowIntentState {
  return {
    samples: [],
    regime: "neutral",
    labeledAt: 0,
    lastNet: null,
    lastPrice: null,
    lastVolume: null,
  };
}

export function clearFlowIntents(): void {
  tracks.clear();
}

export function peekRegime(symbol: string): TapeRegime {
  return tracks.get(normalizeSymbol(symbol))?.regime ?? "neutral";
}

export function observeSymbol(symbol: string, observation: FlowObservation): TapeRegime {
  const key = normalizeSymbol(symbol);
  const next = observeFlow(tracks.get(key) ?? createFlowIntent(), observation);
  tracks.set(key, next);
  return next.regime;
}

export function observeFlow(state: FlowIntentState, observation: FlowObservation): FlowIntentState {
  if (!Number.isFinite(observation.netFlow) || !Number.isFinite(observation.at)) return state;

  const price = finiteOrNull(observation.price);
  const volume = cumulativeVolume(observation);
  if (state.lastNet == null) {
    return {
      ...state,
      lastNet: observation.netFlow,
      lastPrice: price,
      lastVolume: volume,
    };
  }

  const delta = observation.netFlow - state.lastNet;
  const notional = Math.abs(delta);
  const volumeDelta =
    volume != null && state.lastVolume != null && volume >= state.lastVolume ? volume - state.lastVolume : 0;
  const cursor: FlowIntentState = {
    ...state,
    lastNet: observation.netFlow,
    lastPrice: price ?? state.lastPrice,
    lastVolume: volume ?? state.lastVolume,
  };
  if (notional < DUST_NOTIONAL) return cursor;

  const printPrice = price ?? state.lastPrice;
  if (printPrice == null || printPrice <= 0) return cursor;
  const samples = prune(state.samples, observation.at);
  const volumeSize = volumeDelta > 0 ? volumeDelta : notional / printPrice;
  samples.push({
    at: observation.at,
    side: delta > 0 ? 1 : -1,
    price: printPrice,
    volume: volumeSize,
    blockNotional: notional >= BLOCK_NOTIONAL ? notional : 0,
  });
  const regime = resolveRegime(state.regime, state.labeledAt, observation.at, samples);
  return {
    ...cursor,
    samples,
    regime,
    labeledAt: regime === state.regime ? state.labeledAt : observation.at,
  };
}

function resolveRegime(current: TapeRegime, labeledAt: number, now: number, samples: FlowSample[]): TapeRegime {
  const scored = scoreWindow(samples, now);
  const dwellOk = labeledAt === 0 || now - labeledAt >= REGIME_DWELL_MS;
  if (!scored) {
    if (current !== "neutral" && !dwellOk) return current;
    return "neutral";
  }

  const { score, priceSide } = scored;
  const wantAccumulation = score >= REGIME_ENTER && priceSide === "above";
  const wantDistribution = score <= -REGIME_ENTER && priceSide === "below";
  if (current === "neutral") {
    if (wantAccumulation) return "accumulation";
    if (wantDistribution) return "distribution";
    return "neutral";
  }
  if (current === "accumulation") {
    if (wantDistribution && dwellOk) return "distribution";
    if (!wantAccumulation && dwellOk) return "neutral";
    return "accumulation";
  }
  if (wantAccumulation && dwellOk) return "accumulation";
  if (!wantDistribution && dwellOk) return "neutral";
  return "distribution";
}

function scoreWindow(samples: FlowSample[], now: number): { score: number; priceSide: "above" | "below" } | null {
  if (samples.length === 0) return null;
  const span = now - samples[0].at;
  const midpoint = samples[0].at + span / 2;
  let priceVolume = 0;
  let volume = 0;
  let blockBuy = 0;
  let blockSell = 0;
  let earlyBlock = 0;
  let lateBlock = 0;
  for (const sample of samples) {
    priceVolume += sample.price * sample.volume;
    volume += sample.volume;
    if (sample.side > 0) blockBuy += sample.blockNotional;
    else blockSell += sample.blockNotional;
    if (sample.at <= midpoint) earlyBlock += sample.blockNotional;
    else lateBlock += sample.blockNotional;
  }
  const blockTotal = blockBuy + blockSell;
  if (
    span < FLOW_MIN_SPAN_MS ||
    volume <= 0 ||
    blockTotal < BLOCK_NOTIONAL ||
    earlyBlock < BLOCK_NOTIONAL ||
    lateBlock < BLOCK_NOTIONAL
  ) {
    return null;
  }
  const vwap = priceVolume / volume;
  const lastPrice = samples[samples.length - 1].price;
  const priceSide = lastPrice >= vwap ? "above" : "below";
  return { score: (blockBuy - blockSell) / blockTotal, priceSide };
}

function prune(samples: FlowSample[], now: number): FlowSample[] {
  const cutoff = now - FLOW_WINDOW_MS;
  return samples.filter((sample) => sample.at >= cutoff);
}

function cumulativeVolume(observation: FlowObservation): number | null {
  const buy = observation.buyVolume;
  const sell = observation.sellVolume;
  if (buy == null && sell == null) return null;
  const total = (buy ?? 0) + (sell ?? 0);
  return Number.isFinite(total) && total >= 0 ? total : null;
}

function finiteOrNull(value: number | null | undefined): number | null {
  return value != null && Number.isFinite(value) ? value : null;
}

function normalizeSymbol(symbol: string): string {
  return symbol.trim().toUpperCase();
}
