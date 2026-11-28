import type { TaskStatus, Workflow, WorkflowStatus, WorkflowTask } from "../types";

const ACTIVE: WorkflowStatus[] = ["created", "planning", "ready", "running", "waiting_for_approval"];

export const isActiveWorkflow = (status: WorkflowStatus): boolean => ACTIVE.includes(status);

export const STATUS_LABEL: Record<WorkflowStatus, string> = {
  created: "Created",
  planning: "Planning",
  ready: "Ready",
  running: "Running",
  waiting_for_approval: "Waiting for approval",
  completed: "Completed",
  failed: "Failed",
  cancelled: "Cancelled",
};

export const TASK_LABEL: Record<TaskStatus, string> = {
  pending: "Pending",
  ready: "Ready",
  running: "Running",
  waiting_for_approval: "Waiting for approval",
  completed: "Completed",
  failed: "Failed",
  retrying: "Retrying",
  cancelled: "Cancelled",
  blocked: "Blocked",
};

const MARKS: Record<TaskStatus, string> = {
  completed: "✓",
  running: "◉",
  retrying: "◉",
  waiting_for_approval: "◉",
  pending: "○",
  ready: "○",
  failed: "✕",
  blocked: "⊘",
  cancelled: "–",
};

export const taskMark = (status: TaskStatus): string => MARKS[status];

export const progressLabel = (w: Pick<Workflow, "completed_tasks" | "total_tasks">): string =>
  `${w.completed_tasks}/${w.total_tasks} tasks completed`;

/** The task currently waiting on the user's yes/no, if any. */
export function pendingTask(w: Workflow): WorkflowTask | undefined {
  return w.tasks.find(
    (t) => t.status === "waiting_for_approval" && t.pending_approval !== null && t.pending_approval.decision === null
  );
}

/** Which of Continue / Retry failed apply (the server still validates every request). */
export function resumeOptions(w: Workflow): { continue: boolean; retryFailed: boolean } {
  if (w.status === "completed" || w.status === "cancelled" || w.status === "running" || w.status === "planning") {
    return { continue: false, retryFailed: false };
  }
  const done = new Set(w.tasks.filter((t) => t.status === "completed").map((t) => t.id));
  const startable = w.tasks.some(
    (t) => (t.status === "pending" || t.status === "ready") && t.dependencies.every((d) => done.has(d))
  );
  return {
    continue: startable && w.status !== "waiting_for_approval",
    retryFailed: w.status === "failed" && w.tasks.some((t) => t.status === "failed"),
  };
}

/**
 * Which workflows the panel shows: everything still active, plus anything that finished after the page
 * loaded. Old history never appears on its own, and a dismissed one stays hidden.
 */
export function visibleWorkflows(workflows: Workflow[], loadedAtMs: number, dismissed: ReadonlySet<string>): Workflow[] {
  return workflows.filter(
    (w) => !dismissed.has(w.id) && (isActiveWorkflow(w.status) || Date.parse(w.updated_at) >= loadedAtMs)
  );
}

export type EventTone = "ok" | "fail" | "wait" | "info";

export function eventTone(kind: string): EventTone {
  if (kind === "task_failed" || kind === "workflow_failed" || kind === "approval_rejected" || kind === "tool_denied") return "fail";
  if (kind === "permission_requested" || kind === "workflow_waiting" || kind === "task_retrying") return "wait";
  if (kind.endsWith("_completed") || kind === "approval_received" || kind === "plan_generated") return "ok";
  return "info";
}

// ---- Main-screen preview (status line + compact progress) -------------------------------------

const RANK: Record<WorkflowStatus, number> = {
  waiting_for_approval: 0,
  running: 1,
  planning: 1,
  ready: 1,
  created: 1,
  failed: 2,
  completed: 3,
  cancelled: 3,
};

/** The one workflow the main screen previews: approval first, then active work, then failures, then the rest. Ties keep list order (newest first). */
export function focusWorkflow(workflows: Workflow[]): Workflow | undefined {
  return workflows.reduce<Workflow | undefined>((best, w) => (best === undefined || RANK[w.status] < RANK[best.status] ? w : best), undefined);
}

export const WORKFLOW_HEADLINE: Record<WorkflowStatus, string> = {
  created: "PLANNING WORKFLOW",
  planning: "PLANNING WORKFLOW",
  ready: "EXECUTING WORKFLOW",
  running: "EXECUTING WORKFLOW",
  waiting_for_approval: "WAITING FOR APPROVAL",
  completed: "COMPLETED",
  failed: "ERROR",
  cancelled: "CANCELLED",
};

/**
 * Headline and sub-line for the status under the orb. Returns null when the existing ALFRED state should
 * speak for itself: while listening, transcribing, speaking, in an error, or with a chat confirmation open.
 */
export function workflowStatusLine(
  alfredState: string,
  w: Workflow | undefined,
  chatConfirmationOpen: boolean
): { headline: string; subline: string } | null {
  if (!w || chatConfirmationOpen) return null;
  if (alfredState === "listening" || alfredState === "processing" || alfredState === "speaking" || alfredState === "error") return null;
  const subline =
    w.status === "waiting_for_approval" ? "Open Activity to review the action" : w.status === "failed" ? "The workflow did not finish" : "";
  return { headline: WORKFLOW_HEADLINE[w.status], subline };
}

/** What the workflow is doing right now, using only real task data; null when nothing truthful can be said. */
export function currentTaskLine(w: Workflow): string | null {
  const running = w.tasks.find((t) => t.status === "running" || t.status === "retrying");
  if (running) return running.description;
  const waiting = pendingTask(w);
  if (waiting) return `Awaiting approval: ${waiting.pending_approval?.description ?? waiting.description}`;
  switch (w.status) {
    case "created":
    case "planning":
      return "Preparing a plan";
    case "ready":
    case "running":
      return w.tasks.some((t) => t.status === "pending" || t.status === "ready") ? "Preparing the next task" : null;
    case "failed": {
      const failed = w.tasks.find((t) => t.status === "failed");
      return failed ? `${failed.description}${failed.error ? `: ${failed.error}` : ""}` : (w.failure ?? "The workflow did not finish");
    }
    case "completed":
      return "All tasks completed";
    case "cancelled":
      return "Workflow cancelled";
    default:
      return null;
  }
}

/** Short readable task title for the compact timeline (the full text stays in the tooltip). */
export function shortTitle(text: string, max = 28): string {
  const clean = text.replace(/\s+/g, " ").trim();
  if (clean.length <= max) return clean;
  const cut = clean.slice(0, max - 1);
  const space = cut.lastIndexOf(" ");
  return (space > max * 0.5 ? cut.slice(0, space) : cut).replace(/[\s,.;:]+$/, "") + "…";
}

/** Share of tasks actually completed, 0..100. Failed, blocked, running and pending tasks never count. */
export function progressPercent(w: Pick<Workflow, "completed_tasks" | "total_tasks">): number {
  return w.total_tasks > 0 ? Math.round((w.completed_tasks / w.total_tasks) * 100) : 0;
}

export type ActivityIndicator = "working" | "failed" | null;

/** Subtle state for the Activity control: work in progress, or a failure that has not been looked at yet. */
export function activityIndicator(attention: Workflow[]): ActivityIndicator {
  if (attention.some((w) => w.status === "created" || w.status === "planning" || w.status === "ready" || w.status === "running")) return "working";
  return attention.some((w) => w.status === "failed") ? "failed" : null;
}
