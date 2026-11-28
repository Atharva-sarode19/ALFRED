import assert from "node:assert/strict";
import { describe, it } from "node:test";
import type { Workflow, WorkflowTask } from "../src/types.ts";
import {
  activityIndicator,
  currentTaskLine,
  focusWorkflow,
  progressPercent,
  shortTitle,
  workflowStatusLine,
  eventTone,
  isActiveWorkflow,
  pendingTask,
  progressLabel,
  resumeOptions,
  taskMark,
  visibleWorkflows,
} from "../src/utils/workflow.ts";

const task = (id: string, status: WorkflowTask["status"], extra: Partial<WorkflowTask> = {}): WorkflowTask => ({
  id,
  description: id,
  status,
  dependencies: [],
  expected_outcome: "",
  tools: [],
  attempts: 0,
  result_summary: null,
  error: null,
  pending_approval: null,
  ...extra,
});

const wf = (status: Workflow["status"], tasks: WorkflowTask[], extra: Partial<Workflow> = {}): Workflow => ({
  id: "w" + Math.random().toString(16).slice(2),
  title: "t",
  request: "r",
  status,
  tasks,
  failure: null,
  summary: null,
  result: null,
  created_at: "2026-11-27T10:00:00Z",
  updated_at: "2026-11-27T10:00:00Z",
  total_tasks: tasks.length,
  completed_tasks: tasks.filter((t) => t.status === "completed").length,
  ...extra,
});

describe("workflow helpers", () => {
  it("labels progress and marks", () => {
    assert.equal(progressLabel(wf("running", [task("a", "completed"), task("b", "running")])), "1/2 tasks completed");
    assert.equal(taskMark("completed"), "✓");
    assert.equal(taskMark("running"), "◉");
    assert.equal(taskMark("pending"), "○");
  });

  it("knows which statuses are active", () => {
    assert.ok(isActiveWorkflow("running") && isActiveWorkflow("waiting_for_approval"));
    assert.ok(!isActiveWorkflow("completed") && !isActiveWorkflow("failed") && !isActiveWorkflow("cancelled"));
  });

  it("finds only an undecided approval", () => {
    const approval = { tool_name: "notes", arguments: {}, call_id: "c", description: "save", decision: null } as const;
    const waiting = task("b", "waiting_for_approval", { pending_approval: { ...approval } });
    assert.equal(pendingTask(wf("waiting_for_approval", [task("a", "completed"), waiting]))?.id, "b");
    const decided = task("b", "waiting_for_approval", { pending_approval: { ...approval, decision: "approved" } });
    assert.equal(pendingTask(wf("running", [decided])), undefined);
  });

  it("offers Continue only for startable work and Retry only for failures", () => {
    assert.deepEqual(resumeOptions(wf("completed", [task("a", "completed")])), { continue: false, retryFailed: false });
    assert.deepEqual(resumeOptions(wf("running", [task("a", "running")])), { continue: false, retryFailed: false });
    const failed = wf("failed", [task("a", "failed"), task("b", "blocked", { dependencies: ["a"] })]);
    assert.deepEqual(resumeOptions(failed), { continue: false, retryFailed: true });
    const stopped = wf("failed", [task("a", "completed"), task("b", "pending", { dependencies: ["a"] })]);
    assert.deepEqual(resumeOptions(stopped), { continue: true, retryFailed: false });
    const waitingFlow = wf("waiting_for_approval", [task("a", "waiting_for_approval"), task("b", "pending", { dependencies: ["a"] })]);
    assert.deepEqual(resumeOptions(waitingFlow), { continue: false, retryFailed: false });
  });

  it("shows active and newly finished workflows, never old history or dismissed ones", () => {
    const loaded = Date.parse("2026-11-27T12:00:00Z");
    const old = wf("completed", [], { updated_at: "2026-11-27T09:00:00Z" });
    const fresh = wf("completed", [], { updated_at: "2026-11-27T12:05:00Z" });
    const running = wf("running", [], { updated_at: "2026-11-27T09:00:00Z" });
    const shown = visibleWorkflows([old, fresh, running], loaded, new Set()).map((w) => w.id);
    assert.deepEqual(shown, [fresh.id, running.id]);
    assert.deepEqual(visibleWorkflows([fresh, running], loaded, new Set([fresh.id])).map((w) => w.id), [running.id]);
  });

  it("classifies trace events", () => {
    assert.equal(eventTone("task_failed"), "fail");
    assert.equal(eventTone("permission_requested"), "wait");
    assert.equal(eventTone("task_completed"), "ok");
    assert.equal(eventTone("workflow_completed"), "ok");
    assert.equal(eventTone("tool_selected"), "info");
  });
});

describe("main-screen workflow preview", () => {
  const approval = { tool_name: "notes", arguments: {}, call_id: "c", description: "save a note", decision: null } as const;

  it("prefers approval, then active work, then failures, then finished", () => {
    const done = wf("completed", []);
    const failed = wf("failed", []);
    const running = wf("running", []);
    const waiting = wf("waiting_for_approval", []);
    assert.equal(focusWorkflow([done, failed, running, waiting])?.id, waiting.id);
    assert.equal(focusWorkflow([done, failed, running])?.id, running.id);
    assert.equal(focusWorkflow([done, failed])?.id, failed.id);
    assert.equal(focusWorkflow([]), undefined);
  });

  it("maps real workflow status to the headline and yields to other ALFRED states", () => {
    const line = (status: Workflow["status"], state = "idle", confirm = false) =>
      workflowStatusLine(state, wf(status, []), confirm)?.headline ?? null;
    assert.equal(line("planning"), "PLANNING WORKFLOW");
    assert.equal(line("running", "thinking"), "EXECUTING WORKFLOW");
    assert.equal(line("waiting_for_approval"), "WAITING FOR APPROVAL");
    assert.equal(line("completed"), "COMPLETED");
    assert.equal(line("failed"), "ERROR");
    assert.equal(line("running", "listening"), null);
    assert.equal(line("running", "speaking"), null);
    assert.equal(line("running", "idle", true), null);
    assert.equal(workflowStatusLine("idle", undefined, false), null);
  });

  it("describes the current task only from real data", () => {
    const running = wf("running", [task("a", "completed"), task("b", "running", { description: "Compare frameworks" })]);
    assert.equal(currentTaskLine(running), "Compare frameworks");
    const waiting = wf("waiting_for_approval", [task("a", "waiting_for_approval", { pending_approval: { ...approval } })]);
    assert.equal(currentTaskLine(waiting), "Awaiting approval: save a note");
    assert.equal(currentTaskLine(wf("running", [task("a", "completed"), task("b", "pending")])), "Preparing the next task");
    assert.equal(currentTaskLine(wf("running", [task("a", "completed")])), null);
    assert.equal(currentTaskLine(wf("planning", [])), "Preparing a plan");
    assert.match(currentTaskLine(wf("failed", [task("a", "failed", { error: "boom" })])) ?? "", /boom/);
  });

  it("counts only completed tasks as progress", () => {
    const w = wf("running", [task("a", "completed"), task("b", "failed"), task("c", "running"), task("d", "blocked")]);
    assert.equal(w.completed_tasks, 1);
    assert.equal(progressPercent(w), 25);
    assert.equal(progressPercent(wf("planning", [])), 0);
  });

  it("shortens titles readably", () => {
    assert.equal(shortTitle("Search"), "Search");
    const short = shortTitle("Search for information about the selected AI agent frameworks", 28);
    assert.ok(short.length <= 28 && short.endsWith("…") && !short.includes("  "));
  });

  it("shows the activity indicator only for real work or an unseen failure", () => {
    assert.equal(activityIndicator([]), null);
    assert.equal(activityIndicator([wf("running", [])]), "working");
    assert.equal(activityIndicator([wf("failed", []), wf("running", [])]), "working");
    assert.equal(activityIndicator([wf("failed", [])]), "failed");
    assert.equal(activityIndicator([wf("completed", []), wf("waiting_for_approval", [])]), null);
  });
});
