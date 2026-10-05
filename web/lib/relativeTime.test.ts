import assert from "node:assert/strict";

import { formatRelativeAgo } from "./relativeTime";

assert.equal(formatRelativeAgo(2_000), "قبل لحظات");
assert.equal(formatRelativeAgo(12_000), "قبل 12 ثانية");
assert.equal(formatRelativeAgo(60_000), "قبل دقيقة");
assert.equal(formatRelativeAgo(5 * 60_000), "قبل 5 دقائق");
assert.equal(formatRelativeAgo(3 * 3_600_000), "قبل 3 ساعات");

console.log("relative time checks passed");
