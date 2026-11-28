import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { applyTrace } from "../src/utils/activity.ts";

describe("applyTrace", () => {
  it("tracks a tool from selection to completion", () => {
    const ev = applyTrace([], [
      { stage: "input", detail: "Request received" },
      { stage: "tool_selected", detail: "Selected tool: web_search" },
      { stage: "tool_result", detail: "'web_search' completed successfully" },
    ], "t1");
    assert.equal(ev.length, 1);
    assert.equal(ev[0].status, "completed");
  });

  it("walks the approval flow across two responses", () => {
    let ev = applyTrace([], [
      { stage: "tool_selected", detail: "Selected tool: notes" },
      { stage: "confirmation_required", detail: "'notes' needs your confirmation" },
    ], "t1");
    assert.equal(ev[0].status, "waiting");
    assert.equal(ev[0].approval, "required");
    ev = applyTrace(ev, [
      { stage: "confirmed", detail: "You approved 'notes'" },
      { stage: "tool_result", detail: "'notes' failed: disk full" },
    ], "t2");
    assert.equal(ev[0].approval, "approved");
    assert.equal(ev[0].status, "failed");
    assert.equal(ev[0].detail, "disk full");
  });

  it("marks a declined action as failed/declined and records memory notes", () => {
    let ev = applyTrace([], [
      { stage: "tool_selected", detail: "Selected tool: notes" },
      { stage: "confirmation_required", detail: "'notes' needs your confirmation" },
    ], "t1");
    ev = applyTrace(ev, [{ stage: "declined", detail: "You declined 'notes'" }, { stage: "memory_retrieved", detail: "Recalled 2 memories and 0 tasks" }], "t2");
    assert.equal(ev[0].approval, "declined");
    assert.equal(ev[1].kind, "memory");
  });
});

import { formatDuration } from "../src/utils/activity.ts";

describe("durations", () => {
  it("formats readable durations", () => {
    assert.equal(formatDuration(240), "240ms");
    assert.equal(formatDuration(1400), "1.4s");
    assert.equal(formatDuration(3200), "3.2s");
    assert.equal(formatDuration(12_400), "12s");
    assert.equal(formatDuration(65_000), "1m 05s");
  });

  it("keeps the backend-measured duration, and none when it is missing", () => {
    const timed = applyTrace([], [
      { stage: "tool_selected", detail: "Selected tool: calculator" },
      { stage: "tool_result", detail: "'calculator' completed successfully", duration_ms: 12 },
    ], "t1");
    assert.equal(timed[0].durationMs, 12);
    const untimed = applyTrace([], [
      { stage: "tool_selected", detail: "Selected tool: calculator" },
      { stage: "tool_result", detail: "'calculator' completed successfully" },
    ], "t2");
    assert.equal(untimed[0].durationMs, undefined);
  });
});
