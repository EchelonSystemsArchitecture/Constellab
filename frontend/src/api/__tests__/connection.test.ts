import assert from "node:assert/strict";
import { test } from "node:test";
import {
  connectionLabel,
  connectionMessage,
  initialConnection,
  nextConnection,
  reconnectResetsCursor,
  retryDelayMs,
} from "../connection";

const POLICY = { baseDelayMs: 400, maxDelayMs: 5000 };

test("a healthy reply makes the link live and clears the failure counter", () => {
  const live = nextConnection(initialConnection(), { type: "ok", atMs: 1000 }, POLICY);
  assert.equal(live.phase, "live");
  assert.equal(live.attempts, 0);
  assert.equal(live.lastOkAtMs, 1000);
  assert.equal(live.retryDelayMs, 0);
  assert.equal(live.retryAtMs, null);
  assert.equal(reconnectResetsCursor(initialConnection(), live), false);
  assert.equal(connectionLabel(live), "LINK LIVE");
});

test("the first late reply degrades the link, then it reports offline with backoff", () => {
  const live = nextConnection(initialConnection(), { type: "ok", atMs: 1000 }, POLICY);
  const degraded = nextConnection(live, { type: "failure", atMs: 1200, message: "HTTP 503" }, POLICY);
  assert.equal(degraded.phase, "degraded");
  assert.equal(degraded.attempts, 1);
  assert.equal(degraded.retryDelayMs, 400);
  assert.equal(degraded.retryAtMs, 1600);
  assert.equal(degraded.lastOkAtMs, 1000, "the last good reply time is retained");

  const down = nextConnection(degraded, { type: "failure", atMs: 1700, message: "fetch failed" }, POLICY);
  assert.equal(down.phase, "down");
  assert.equal(down.attempts, 2);
  assert.equal(down.retryDelayMs, 800);
  assert.match(connectionMessage(down, 1800), /retrying in 0\.7 s/);
  assert.match(connectionMessage(down, 1800), /fetch failed/);
});

test("a broken link never claims to be degraded before it was ever live", () => {
  const down = nextConnection(initialConnection(), { type: "failure", atMs: 10, message: "ECONNREFUSED" }, POLICY);
  assert.equal(down.phase, "down");
  assert.equal(connectionLabel(down), "CORE OFFLINE");
});

test("backoff grows exponentially and is capped", () => {
  assert.equal(retryDelayMs(0, POLICY), 0);
  assert.equal(retryDelayMs(1, POLICY), 400);
  assert.equal(retryDelayMs(2, POLICY), 800);
  assert.equal(retryDelayMs(3, POLICY), 1600);
  assert.equal(retryDelayMs(4, POLICY), 3200);
  assert.equal(retryDelayMs(5, POLICY), 5000);
  assert.equal(retryDelayMs(50, POLICY), 5000);
});

test("a contract rejection is reported as invalid, distinct from a lost link", () => {
  const live = nextConnection(initialConnection(), { type: "ok", atMs: 0 }, POLICY);
  const invalid = nextConnection(live, { type: "invalid", atMs: 500, message: "satellites[0].orbit" }, POLICY);
  assert.equal(invalid.phase, "invalid");
  assert.equal(connectionLabel(invalid), "REPLY REJECTED");
  assert.match(connectionMessage(invalid, 500), /satellites\[0\]\.orbit/);
});

test("recovery after a lost link resets the revision cursor; a normal reply does not", () => {
  const live = nextConnection(initialConnection(), { type: "ok", atMs: 0 }, POLICY);
  const down = nextConnection(live, { type: "failure", atMs: 100, message: "gone" }, POLICY);
  const recovered = nextConnection(down, { type: "ok", atMs: 200 }, POLICY);
  assert.equal(recovered.phase, "live");
  assert.equal(reconnectResetsCursor(down, recovered), true);
  assert.equal(reconnectResetsCursor(live, nextConnection(live, { type: "ok", atMs: 300 }, POLICY)), false);
  // A first-ever connection has no old revision epoch to forget.
  assert.equal(reconnectResetsCursor(initialConnection(), live), false);
});
