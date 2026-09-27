import type { TapeRegime } from "@/lib/liquidity";

/** Lookback for the volume- and price-weighted institutional intent. */
export const FLOW_WINDOW_MS = 180_000;
/** A side is shown only after the tape has covered about two minutes. */
export const FLOW_MIN_SPAN_MS = 120_000;
/** |score| must clear this before تجميع or تصريف is treated as real. */
export const REGIME_ENTER = 0.3;
/** Inside this band the previous real label can fall back to توازن. */
export const REGIME_EXIT = 0.12;
/** A shown side stays up at least this long before it may switch. */
export const REGIME_DWELL_MS = 45_000;
/** Ignore riyal-level noise. Meaningful flow matches the live signal floor. */
export const FLOW_MIN_NOTIONAL = 15_000;
const HALF_LIFE_MS = 60_000;
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
  size: number;
  notional: number;
  priceDelta: number;
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
  const priceDelta = price != null && state.lastPrice != null ? price - state.lastPrice : 0;
  const volumeDelta =
    volume != null && state.lastVolume != null && volume >= state.lastVolume ? volume - state.lastVolume : 0;
  const cursor: FlowIntentState = {
    ...state,
    lastNet: observation.netFlow,
    lastPrice: price ?? state.lastPrice,
    lastVolume: volume ?? state.lastVolume,
  };
  if (notional < DUST_NOTIONAL) return cursor;

  const samples = prune(state.samples, observation.at);
  samples.push({
    at: observation.at,
    side: delta > 0 ? 1 : -1,
    size: volumeDelta > 0 ? volumeDelta : notional,
    notional,
    priceDelta,
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

  const { score } = scored;
  const wantAccumulation = score >= REGIME_ENTER;
  const wantDistribution = score <= -REGIME_ENTER;
  if (current === "neutral") {
    if (wantAccumulation) return "accumulation";
    if (wantDistribution) return "distribution";
    return "neutral";
  }
  if (current === "accumulation") {
    if (wantDistribution && dwellOk) return "distribution";
    if (score < REGIME_EXIT && dwellOk) return "neutral";
    return "accumulation";
  }
  if (wantAccumulation && dwellOk) return "accumulation";
  if (score > -REGIME_EXIT && dwellOk) return "neutral";
  return "distribution";
}

function scoreWindow(samples: FlowSample[], now: number): { score: number } | null {
  if (samples.length === 0) return null;
  const span = now - samples[0].at;
  const midpoint = samples[0].at + span / 2;
  let notional = 0;
  let earlyNotional = 0;
  let lateNotional = 0;
  let weightedSide = 0;
  let weight = 0;
  for (const sample of samples) {
    notional += sample.notional;
    if (sample.at <= midpoint) earlyNotional += sample.notional;
    else lateNotional += sample.notional;
    const age = Math.max(0, now - sample.at);
    const recency = Math.exp((-Math.LN2 * age) / HALF_LIFE_MS);
    const sampleWeight = sample.size * recency * priceConfirm(sample.side, sample.priceDelta);
    weightedSide += sample.side * sampleWeight;
    weight += sampleWeight;
  }
  const halfFloor = FLOW_MIN_NOTIONAL * 0.25;
  if (
    span < FLOW_MIN_SPAN_MS ||
    notional < FLOW_MIN_NOTIONAL ||
    earlyNotional < halfFloor ||
    lateNotional < halfFloor ||
    weight <= 0
  ) {
    return null;
  }
  return { score: weightedSide / weight };
}

function priceConfirm(side: 1 | -1, priceDelta: number): number {
  if (priceDelta === 0) return 1;
  return Math.sign(priceDelta) === side ? 1.15 : 0.85;
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
