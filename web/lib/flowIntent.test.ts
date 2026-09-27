import assert from "node:assert/strict";

import { createFlowIntent, observeFlow, type FlowIntentState } from "./flowIntent";
import { holdDisplayedRows } from "./radarHold";

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

const burst = runTape(20, 2, (elapsed) => ({
  net: elapsed * 5_000,
  price: 10 + elapsed * 0.01,
  buy: elapsed * 100,
  sell: 0,
}));
assert.equal(burst.regime, "neutral");

const chop = runTape(180, 2, (elapsed) => {
  const buySide = Math.floor(elapsed / 2) % 2 === 0;
  const prints = elapsed / 2;
  return {
    net: buySide ? prints * 1_000 : prints * -200,
    price: 10 + (buySide ? 0.01 : -0.01),
    buy: buySide ? prints * 50 : (prints - 1) * 50,
    sell: buySide ? (prints - 1) * 40 : prints * 40,
  };
});
assert.equal(chop.regime, "neutral");

const accumulated = runTape(130, 2, (elapsed) => ({
  net: elapsed * 2_000,
  price: 10 + elapsed * 0.02,
  buy: elapsed * 80,
  sell: 10,
}));
assert.equal(accumulated.regime, "accumulation");

let flipped = accumulated;
let net = 130 * 2_000;
let buy = 130 * 80;
let sell = 10;
let price = 10 + 130 * 0.02;
for (let extra = 2; extra <= 8; extra += 2) {
  net -= 8_000;
  sell += 200;
  price -= 0.05;
  flipped = step(flipped, (130 + extra) * 1000, net, price, buy, sell);
}
assert.equal(flipped.regime, "accumulation");

let distributed = flipped;
for (let extra = 10; extra <= 200; extra += 2) {
  net -= 3_000;
  sell += 90;
  price -= 0.02;
  distributed = step(distributed, (130 + extra) * 1000, net, price, buy, sell);
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
assert.deepEqual(
  early.map((item) => item.row),
  [
    { symbol: "1120", name: "الراجحي", price: 80 },
    { symbol: "2222", name: "أرامكو", price: 27 },
  ],
);
const later = holdDisplayedRows(early, [{ symbol: "2222", name: "أرامكو", price: 28 }], 45_000);
assert.deepEqual(
  later.map((item) => ({ symbol: item.symbol, price: item.row.price })),
  [{ symbol: "2222", price: 28 }],
);

console.log("flow intent and radar hold checks passed");
