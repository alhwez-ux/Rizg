import assert from "node:assert/strict";

import { OPEN_POLL_MS, sessionPollMs } from "./sessionPoll";

const open = new Date("2026-10-08T07:05:00.000Z");
const justBefore = new Date("2026-10-08T06:29:30.000Z");
const closed = new Date("2026-10-08T13:00:00.000Z");

assert.equal(sessionPollMs(60_000, open), OPEN_POLL_MS);
assert.equal(sessionPollMs(2_000, open), 2_000);
assert.ok(sessionPollMs(60_000, justBefore) <= 31_000);
assert.equal(sessionPollMs(45_000, closed), 45_000);

console.log("session poll checks passed");
