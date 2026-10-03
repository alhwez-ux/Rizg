import assert from "node:assert/strict";

import { createFlowIntent, observeFlow, type FlowIntentState } from "./flowIntent";
import { authoritativeTickPrice } from "./livePrice";
import { holdDisplayedRows } from "./radarHold";
import type { LiquidityTick } from "./liquidity";

function step(
  state: FlowIntentState,
  at: number,
  net: number,
  price: number,
  buy: number,
  sell: number,
): FlowIntentState {
  return observeFlow(state, { at, netFlow: net, price, buyVolume: buy, sellVolume: sell });
}

function runTape(
  seconds: number,
  every: number,
  apply: (elapsed: number) => { net: number; price: number; buy: number; sell: number },
): FlowIntentState {
  let state = step(createFlowIntent(), 0, 0, 10, 0, 0);
  for (let elapsed = every; elapsed <= seconds; elapsed += every) {
    const point = apply(elapsed);
    state = step(state, elapsed * 1000, point.net, point.price, point.buy, point.sell);
  }
  return state;
}

const burst = runTape(40, 10, (elapsed) => ({
  net: (elapsed / 10) * 150_000,
  price: 10 + elapsed * 0.01,
  buy: elapsed * 100,
  sell: 0,
}));
assert.equal(burst.regime, "neutral");

const noise = runTape(320, 10, (elapsed) => ({
  net: elapsed * 2_000,
  price: 10 + elapsed * 0.002,
  buy: elapsed * 20,
  sell: 1,
}));
assert.equal(noise.regime, "neutral");

const accumulated = runTape(320, 10, (elapsed) => ({
  net: (elapsed / 10) * 150_000,
  price: 10 + elapsed * 0.01,
  buy: elapsed * 100,
  sell: 0,
}));
assert.equal(accumulated.regime, "accumulation");

let heldSide = accumulated;
let net = (320 / 10) * 150_000;
let buy = 320 * 100;
let sell = 0;
let price = 10 + 320 * 0.01;
for (let extra = 10; extra <= 20; extra += 10) {
  net -= 150_000;
  sell += 1_000;
  price -= 0.4;
  heldSide = step(heldSide, (320 + extra) * 1000, net, price, buy, sell);
}
assert.equal(heldSide.regime, "accumulation");

let distributed = heldSide;
for (let extra = 30; extra <= 340; extra += 10) {
  net -= 150_000;
  sell += 1_000;
  price -= 0.05;
  distributed = step(distributed, (320 + extra) * 1000, net, price, buy, sell);
}
assert.equal(distributed.regime, "distribution");

const held = holdDisplayedRows(
  [],
  [
    { symbol: "1120", name: "الراجحي", price: 80 },
    { symbol: "2222", name: "أرامكو", price: 27 },
  ],
  0,
);
const early = holdDisplayedRows(held, [{ symbol: "2222", name: "أرامكو", price: 28 }], 10_000);
assert.equal(early.length, 2);
assert.equal(early[0].row.price, 80);
const stillHeld = holdDisplayedRows(early, [{ symbol: "2222", name: "أرامكو", price: 28 }], 45_000);
assert.equal(stillHeld.length, 2);
const later = holdDisplayedRows(early, [{ symbol: "2222", name: "أرامكو", price: 28 }], 60_000);
assert.deepEqual(
  later.map((item) => item.symbol),
  ["2222"],
);

const tick = {
  symbol: "4263",
  lastPrice: 18.42,
  price: 18.1,
} as LiquidityTick;
assert.equal(authoritativeTickPrice("4263", tick), 18.42);
assert.equal(authoritativeTickPrice("1120", tick), null);
assert.equal(authoritativeTickPrice("4263", null), null);

console.log("flow intent and radar hold checks passed");
