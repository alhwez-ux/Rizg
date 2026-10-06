import assert from "node:assert/strict";

import { graduatedTargets } from "./tradeTargets";

const plan = graduatedTargets(63.45, 62.82);
assert.deepEqual(plan, { t1: 64.08, t2: 64.71, t3: 65.34 });

const withRange = graduatedTargets(100, 98, [101.2, 106]);
assert.equal(withRange?.t1, 101.2);
assert.equal(withRange?.t2, 104);
assert.equal(withRange?.t3, 106);

assert.equal(graduatedTargets(10, 10), null);
assert.equal(graduatedTargets(10, 11), null);

console.log("trade target checks passed");
