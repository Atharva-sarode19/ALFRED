import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  DRAG_RADIANS_PER_PX,
  DRAG_THRESHOLD_PX,
  OrbDrag,
  easeAutoSpin,
  insideOrb,
  silhouetteRadius,
} from "../src/orb/orbDrag.ts";
import { OrbController } from "../src/orb/orbController.ts";

describe("OrbDrag: which presses can rotate the orb", () => {
  it("a press that starts outside the orb never rotates it, however far it moves", () => {
    const drag = new OrbDrag();
    assert.equal(drag.begin(1, 500, 500, false), false);
    assert.equal(drag.tracking, false);
    assert.equal(drag.move(1, 700, 700), null);
    assert.equal(drag.dragging, false);
  });

  it("a click (press and release without moving) is not a drag", () => {
    const drag = new OrbDrag();
    drag.begin(1, 100, 100, true);
    assert.equal(drag.move(1, 102, 101), null);
    assert.equal(drag.end(1), false);
  });

  it("small jitter under the threshold is still a click", () => {
    const drag = new OrbDrag();
    drag.begin(1, 100, 100, true);
    assert.equal(drag.move(1, 100 + DRAG_THRESHOLD_PX - 1, 100), null);
    assert.equal(drag.dragging, false);
  });
});

describe("OrbDrag: rotation", () => {
  it("crossing the threshold starts the drag and applies the distance moved so far (no slip under the cursor)", () => {
    const drag = new OrbDrag();
    drag.begin(1, 100, 100, true);
    const first = drag.move(1, 110, 100)!;
    assert.equal(first.started, true);
    assert.ok(Math.abs(first.dyaw - 10 * DRAG_RADIANS_PER_PX) < 1e-12);
    assert.equal(first.dpitch, 0);
    assert.equal(drag.dragging, true);
  });

  it("moving right turns the orb right (+yaw) and moving down turns it down (+pitch), 1:1 with the cursor", () => {
    const drag = new OrbDrag();
    drag.begin(1, 0, 0, true);
    drag.move(1, 20, 0);
    const right = drag.move(1, 50, 0)!;
    assert.ok(right.dyaw > 0 && right.dpitch === 0 && !right.started);
    const down = drag.move(1, 50, 40)!;
    assert.ok(down.dpitch > 0 && down.dyaw === 0);
    const left = drag.move(1, 20, 40)!;
    const up = drag.move(1, 20, 0)!;
    assert.ok(left.dyaw < 0 && up.dpitch < 0);
    assert.ok(Math.abs(right.dyaw - 30 * DRAG_RADIANS_PER_PX) < 1e-12);
  });

  it("moves add up to exactly the cursor travel, so the orb ends where the cursor says", () => {
    const drag = new OrbDrag();
    drag.begin(1, 200, 200, true);
    let yaw = 0;
    let pitch = 0;
    for (const [x, y] of [[230, 205], [260, 190], [255, 150], [300, 140]]) {
      const m = drag.move(1, x, y)!;
      yaw += m.dyaw;
      pitch += m.dpitch;
    }
    assert.ok(Math.abs(yaw - 100 * DRAG_RADIANS_PER_PX) < 1e-9);
    assert.ok(Math.abs(pitch - -60 * DRAG_RADIANS_PER_PX) < 1e-9);
  });

  it("once started, a drag keeps following the pointer after it leaves the orb, until release", () => {
    const drag = new OrbDrag();
    drag.begin(1, 100, 100, true);
    drag.move(1, 120, 100);
    const outside = drag.move(1, 9000, 9000);
    assert.ok(outside && outside.dyaw > 0);
  });

  it("release ends the drag, later moves do nothing, ending twice is safe", () => {
    const drag = new OrbDrag();
    drag.begin(1, 0, 0, true);
    drag.move(1, 30, 0);
    assert.equal(drag.end(1), true);
    assert.equal(drag.move(1, 90, 0), null);
    assert.equal(drag.end(1), false);
    assert.equal(drag.tracking, false);
  });

  it("another pointer cannot steer or end the drag", () => {
    const drag = new OrbDrag();
    drag.begin(1, 0, 0, true);
    drag.move(1, 30, 0);
    assert.equal(drag.move(2, 500, 500), null);
    assert.equal(drag.end(2), false);
    assert.equal(drag.dragging, true);
  });

  it("can start a fresh drag right after the last one with no leftover state", () => {
    const drag = new OrbDrag();
    drag.begin(1, 0, 0, true);
    drag.move(1, 40, 0);
    drag.end(1);
    drag.begin(2, 300, 300, true);
    assert.equal(drag.move(2, 302, 300), null);
    const m = drag.move(2, 320, 300)!;
    assert.ok(m.started && Math.abs(m.dyaw - 20 * DRAG_RADIANS_PER_PX) < 1e-12);
  });
});

describe("hit testing the orb", () => {
  it("silhouette is the sphere radius enlarged by perspective", () => {
    assert.equal(silhouetteRadius(0, 4), 0);
    assert.ok(Math.abs(silhouetteRadius(1, 4) - 4 / 3) < 1e-12);
    assert.ok(silhouetteRadius(2, 4.2) > silhouetteRadius(1, 4.2));
    assert.equal(silhouetteRadius(5, 4), Number.POSITIVE_INFINITY);
  });

  it("insideOrb is true on the orb and false off it", () => {
    assert.equal(insideOrb(300, 300, 300, 300, 100), true);
    assert.equal(insideOrb(390, 300, 300, 300, 100), true);
    assert.equal(insideOrb(300, 405, 300, 300, 100, 2), false);
    assert.equal(insideOrb(450, 450, 300, 300, 100), false); // inside the square, outside the circle
  });
});

describe("automatic rotation hand-over", () => {
  function run(from: number, hold: boolean, seconds: number, fps = 60) {
    const values = [from];
    for (let i = 0; i < seconds * fps; i++) values.push(easeAutoSpin(values[values.length - 1], hold, 1 / fps));
    return values;
  }

  it("slows to a stop while dragging, without ever jumping", () => {
    const v = run(1, true, 2);
    for (let i = 1; i < v.length; i++) {
      assert.ok(v[i] <= v[i - 1] + 1e-12, "monotonic");
      assert.ok(v[i - 1] - v[i] < 0.07, "smooth step");
    }
    assert.ok(v[v.length - 1] < 0.001);
  });

  it("resumes smoothly from wherever it was when the drag ends", () => {
    const v = run(0.3, false, 3);
    for (let i = 1; i < v.length; i++) {
      assert.ok(v[i] >= v[i - 1] - 1e-12);
      assert.ok(v[i] - v[i - 1] < 0.07);
    }
    assert.ok(v[v.length - 1] > 0.999 && v[v.length - 1] <= 1);
  });

  it("is frame-rate independent", () => {
    const slow = run(1, true, 1, 30);
    const fast = run(1, true, 1, 120);
    assert.ok(Math.abs(slow[slow.length - 1] - fast[fast.length - 1]) < 1e-9);
  });
});

describe("OrbController dragging flag", () => {
  it("is off by default, shows up in the snapshot, and survives reset()", () => {
    const c = new OrbController();
    assert.equal(c.step(0.016).dragging, false);
    c.setDragging(true);
    assert.equal(c.dragging, true);
    assert.equal(c.step(0.016).dragging, true);
    c.reset();
    assert.equal(c.dragging, true);
    c.setDragging(false);
    assert.equal(c.step(0.016).dragging, false);
  });

  it("manual rotation keeps working while dragging, and eases rather than jumps", () => {
    const c = new OrbController();
    c.setDragging(true);
    c.rotateBy(0.5, -0.3);
    const first = c.step(1 / 60);
    assert.ok(first.yaw > 0 && first.yaw < 0.5);
    for (let i = 0; i < 120; i++) c.step(1 / 60);
    const done = c.step(1 / 60);
    assert.ok(Math.abs(done.yaw - 0.5) < 0.01 && Math.abs(done.pitch + 0.3) < 0.01);
  });
});
