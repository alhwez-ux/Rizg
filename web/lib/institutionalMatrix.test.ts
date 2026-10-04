import assert from "node:assert/strict";

import { accumulationBoard, distributionBoard, entryBoard, exitBoard } from "./institutionalMatrix";
import type { ScreenerRow } from "./screener";
import type { SmartMoneyRow } from "./smartMoney";

function screener(patch: Partial<ScreenerRow> & Pick<ScreenerRow, "symbol">): ScreenerRow {
  return {
    name: patch.symbol,
    price: 10,
    change_percent: 0,
    volume: 1,
    value: 1,
    inflow: 0,
    outflow: 0,
    net_flow: 0,
    buy_volume: 0,
    sell_volume: 0,
    buy_ratio: null,
    sell_ratio: null,
    volume_surge: null,
    score: 1,
    entry_signal: false,
    exit_signal: false,
    recommendation: null,
    unexpected: false,
    flow_verified: true,
    tracked: false,
    vwap: null,
    atr: null,
    bid: null,
    ask: null,
    book_pressure: null,
    suggested_entry: null,
    suggested_exit: null,
    target_price: null,
    stop_loss: null,
    reasons: [],
    sources: [],
    updated_at: null,
    ...patch,
  };
}

function money(patch: Partial<SmartMoneyRow> & Pick<SmartMoneyRow, "symbol" | "signal_kind">): SmartMoneyRow {
  return {
    name: patch.symbol,
    sector: "",
    last_price: 10,
    institutional_flow_score: 1,
    inst_share_pct: 0,
    retail_share_pct: 0,
    institutional_mfi: null,
    retail_mfi: null,
    block_trades: 1,
    last_block_value: null,
    clustered: 0,
    clustered_buys: 0,
    cluster_run: 0,
    near_bid_wall: false,
    signal: "",
    badge: "",
    reason: "مؤكد",
    entry: null,
    target: null,
    stop: null,
    plan_ok: false,
    score: 1,
    ...patch,
  };
}

const rows = [
  screener({ symbol: "1120", entry_signal: true, score: 4, net_flow: 2_000_000, reasons: ["كتل شراء"] }),
  screener({ symbol: "2222", exit_signal: true, score: 9, net_flow: -500_000, reasons: ["كتل بيع"] }),
  screener({ symbol: "2010", entry_signal: true, exit_signal: true, score: 20 }),
];

assert.deepEqual(
  entryBoard(rows, "all").map((card) => card.symbol),
  ["1120"],
);
assert.equal(entryBoard(rows, "all")[0]?.reason, "كتل شراء");
assert.deepEqual(
  exitBoard(rows, "all").map((card) => card.symbol),
  ["2222"],
);

const funds = [
  money({ symbol: "1120", signal_kind: "accumulation", plan_ok: true, institutional_flow_score: 3 }),
  money({ symbol: "7010", signal_kind: "accumulation", plan_ok: false, institutional_flow_score: 9 }),
  money({ symbol: "2222", signal_kind: "distribution", institutional_flow_score: 5 }),
  money({ symbol: "1180", signal_kind: "watch", institutional_flow_score: 8 }),
];

assert.deepEqual(
  accumulationBoard(funds, "all").map((card) => card.symbol),
  ["1120"],
);
assert.deepEqual(
  distributionBoard(funds, "all").map((card) => card.symbol),
  ["2222"],
);

console.log("institutional matrix checks passed");
