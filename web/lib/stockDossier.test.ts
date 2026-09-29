import assert from "node:assert/strict";

import { overlayTickOnReport, type LiveRadarReport } from "./liveRadar";
import { buildStockDossier, liquidityScore } from "./stockDossier";
import type { LiquidityTick } from "./liquidity";

const rajhi = buildStockDossier("1120", 100, {
  quote_mode: "live",
  buy_ratio: 0.8,
  volume_ratio: 2,
  block_trades: 3,
});

assert.equal(rajhi.shariah, "PURE");
assert.equal(rajhi.peRatio, 15.56);
assert.equal(rajhi.dividendYieldPct, 2.53);
assert.equal(rajhi.debtToMarket, 0.04);
assert.equal(rajhi.fairValue, 96.4);
assert.equal(rajhi.healthScore, 75.6);
assert.equal(rajhi.liquidityScore, 72.5);

const waiting = buildStockDossier("1120", null, {
  quote_mode: "last_close",
  buy_ratio: 0.9,
  volume_ratio: 4,
  block_trades: 5,
});
assert.equal(waiting.fairValue, null);
assert.equal(waiting.liquidityScore, null);

assert.equal(buildStockDossier("1010", 40, null).shariah, "PROHIBITED");
assert.equal(liquidityScore({ quote_mode: "live", buy_ratio: 0.9, volume_ratio: 8, block_trades: 0 }), 75.5);

const report = {
  symbol: "4263",
  signal: "neutral",
  entry: false,
  exit: false,
  trap: null,
  flow_verified: false,
  score: 0,
  net_flow: 10,
  inflow: 10,
  outflow: 0,
  buy_volume: 1,
  sell_volume: 1,
  buy_ratio: 0.99,
  sell_ratio: 0.01,
  last_price: 9,
  vwap: null,
  atr: null,
  suggested_entry: null,
  suggested_exit: null,
  target_price: null,
  stop_loss: null,
  change_percent: 4,
  trade_count: 1,
  reasons: [],
  quote_mode: "last_close",
} satisfies LiveRadarReport;

const tick = {
  type: "tick",
  symbol: "4263",
  netFlow: 250_000,
  inflow: 250_000,
  outflow: 0,
  buyVolume: 300,
  sellVolume: 100,
  lastPrice: 18.42,
  lastSide: "BUY",
  tick: null,
  side: "BUY",
  price: 18.42,
  volume: 400,
  moneyFlow: null,
  tradeCount: 4,
  timestamp: null,
  recommendation: null,
} satisfies LiquidityTick;

const overlaid = overlayTickOnReport(report, tick);
assert.equal(overlaid.last_price, 18.42);
assert.equal(overlaid.quote_mode, "live");
assert.equal(overlaid.buy_ratio, 0.75);
assert.equal(overlaid.sell_ratio, 0.25);
assert.equal(overlayTickOnReport(report, null).last_price, 9);
assert.equal(overlayTickOnReport(report, null).quote_mode, "last_close");
assert.equal(overlayTickOnReport(report, null).net_flow, 10);

console.log("stock dossier checks passed");
