import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { OrbController, PITCH_LIMIT, SCALE_MAX, SCALE_MIN } from "../src/orb/orbController.ts";

function settle(c: OrbController, seconds = 3) {
  let snap = c.step(0);
  for (let i = 0; i < seconds * 60; i++) snap = c.step(1 / 60);
  return snap;
}

describe("OrbController", () => {
  it("eases toward rotation targets instead of jumping", () => {
    const c = new OrbController();
    c.rotateBy(1, 0.5);
    const first = c.step(1 / 60);
    assert.ok(first.yaw > 0 && first.yaw < 1);
    const done = settle(c);
    assert.ok(Math.abs(done.yaw - 1) < 0.01 && Math.abs(done.pitch - 0.5) < 0.01);
  });

  it("clamps pitch and scale", () => {
    const c = new OrbController();
    c.rotateBy(0, 50);
    c.setScale(99);
    const done = settle(c);
    assert.ok(done.pitch <= PITCH_LIMIT + 1e-6);
    assert.ok(done.scale <= SCALE_MAX + 1e-6);
    c.setScale(0.01);
    assert.ok(settle(c).scale >= SCALE_MIN - 1e-6);
  });

  it("zoomBy multiplies the target and respects limits", () => {
    const c = new OrbController();
    c.zoomBy(1.2);
    assert.ok(Math.abs(c.targetScale - 1.2) < 1e-9);
    c.zoomBy(10);
    assert.equal(c.targetScale, SCALE_MAX);
  });

  it("toggles pause", () => {
    const c = new OrbController();
    assert.equal(c.togglePaused(), true);
    assert.equal(c.step(0.016).paused, true);
    assert.equal(c.togglePaused(), false);
  });

  it("level rises faster than it falls and ignores bad numbers", () => {
    const c = new OrbController();
    c.setLevel(1);
    const up = c.step(0.05).level;
    c.setLevel(0);
    const down = 1 - c.step(0.05).level; // from a lower starting point, so compare rates loosely
    assert.ok(up > 0.7);
    assert.ok(down < up);
    c.setLevel(Number.NaN);
    assert.ok(Number.isFinite(c.step(0.016).level));
  });

  it("reset restores defaults", () => {
    const c = new OrbController();
    c.rotateBy(2, 1);
    c.setScale(1.3);
    c.setPaused(true);
    c.reset();
    const done = settle(c);
    assert.ok(Math.abs(done.yaw) < 0.01 && Math.abs(done.scale - 1) < 0.01 && !done.paused);
  });
});
