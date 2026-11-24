import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { rmsOf } from "../src/utils/audioLevel.ts";

describe("rmsOf", () => {
  it("is zero for silence and for an empty buffer", () => {
    assert.equal(rmsOf(new Float32Array(512)), 0);
    assert.equal(rmsOf([]), 0);
  });

  it("matches the known RMS of a full-scale square wave and a sine", () => {
    assert.ok(Math.abs(rmsOf([1, -1, 1, -1]) - 1) < 1e-9);
    const sine = Array.from({ length: 1000 }, (_, i) => Math.sin((i / 1000) * Math.PI * 2 * 10));
    assert.ok(Math.abs(rmsOf(sine) - Math.SQRT1_2) < 0.01);
  });

  it("scales with amplitude", () => {
    assert.ok(rmsOf([0.5, -0.5]) < rmsOf([1, -1]));
  });
});
