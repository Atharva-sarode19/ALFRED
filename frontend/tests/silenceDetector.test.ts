import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { SilenceDetector } from "../src/utils/silenceDetector.ts";

/** Drive the detector with a level profile sampled every 50 ms; returns the first non-continue verdict. */
function drive(levelAt: (ms: number) => number, totalMs = 30000) {
  const d = new SilenceDetector();
  for (let t = 0; t <= totalMs; t += 50) {
    const v = d.push(levelAt(t), t);
    if (v !== "continue") return { verdict: v, at: t };
  }
  return { verdict: "continue" as const, at: totalMs };
}

describe("SilenceDetector", () => {
  it("stops shortly after speech ends", () => {
    const r = drive((t) => (t >= 600 && t < 2600 ? 0.12 : 0.004));
    assert.equal(r.verdict, "stop");
    assert.ok(r.at >= 2600 + 1000 && r.at <= 2600 + 1300, `stopped at ${r.at}`);
  });

  it("aborts when nobody speaks (never sends silence)", () => {
    const r = drive(() => 0.004);
    assert.equal(r.verdict, "abort");
    assert.ok(r.at >= 6000 && r.at < 6200);
  });

  it("does not treat a short click as speech", () => {
    const r = drive((t) => (t >= 1000 && t < 1060 ? 0.3 : 0.004));
    assert.equal(r.verdict, "abort");
  });

  it("copes with a noisy room (steady hum below the speech level)", () => {
    const r = drive((t) => (t >= 800 && t < 2800 ? 0.15 : 0.012));
    assert.equal(r.verdict, "stop");
  });

  it("still works if the user starts talking immediately", () => {
    const r = drive((t) => (t < 2000 ? 0.1 : 0.004));
    assert.equal(r.verdict, "stop");
  });

  it("caps a recording that never goes quiet", () => {
    const r = drive(() => 0.2);
    assert.equal(r.verdict, "stop");
    assert.ok(r.at >= 20000 && r.at < 20100);
  });
});
