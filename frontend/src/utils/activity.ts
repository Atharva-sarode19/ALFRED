import type { ActivityEvent, TraceStep } from "../types";

const quoted = /'([^']+)'/;
const toolName = (detail: string) => quoted.exec(detail)?.[1];

function findOpen(events: ActivityEvent[], name: string | undefined, statuses: ActivityEvent["status"][]): number {
  for (let i = events.length - 1; i >= 0; i--) {
    const e = events[i];
    if (e.kind === "tool" && e.name === name && statuses.includes(e.status)) return i;
  }
  return -1;
}

/**
 * Fold one response's backend trace into the running activity list. Nothing is invented: every
 * event comes from a trace step the orchestrator emitted (tool selection, confirmation,
 * result, memory notes, errors). The backend does not report durations, so none are shown.
 */
export function applyTrace(previous: ActivityEvent[], steps: TraceStep[], idPrefix: string): ActivityEvent[] {
  const events = previous.map((e) => ({ ...e }));
  const add = (event: Omit<ActivityEvent, "id">) => events.push({ ...event, id: `${idPrefix}-${events.length}` });

  for (const { stage, detail, duration_ms } of steps) {
    const name = toolName(detail);
    const durationMs = typeof duration_ms === "number" && duration_ms >= 0 ? duration_ms : undefined;
    switch (stage) {
      case "tool_selected": {
        const tool = detail.replace(/^Selected tool:\s*/, "");
        add({ name: tool, kind: "tool", status: "pending" });
        break;
      }
      case "confirmation_required": {
        const i = findOpen(events, name, ["pending"]);
        if (i >= 0) events[i] = { ...events[i], status: "waiting", approval: "required" };
        break;
      }
      case "confirmed": {
        const i = findOpen(events, name, ["waiting"]);
        if (i >= 0) events[i] = { ...events[i], status: "pending", approval: "approved" };
        break;
      }
      case "declined":
      case "abandoned": {
        const i = findOpen(events, name, ["waiting"]);
        if (i >= 0) events[i] = { ...events[i], status: "failed", approval: "declined", detail: stage === "declined" ? "Declined" : "Not confirmed, skipped" };
        break;
      }
      case "tool_denied": {
        const i = findOpen(events, name, ["pending"]);
        if (i >= 0) events[i] = { ...events[i], status: "failed", detail: "Not permitted" };
        else add({ name: name ?? "tool", kind: "tool", status: "failed", detail: "Not permitted" });
        break;
      }
      case "tool_result": {
        const failed = /failed/.test(detail);
        const i = findOpen(events, name, ["pending", "running"]);
        const text = failed ? detail.replace(/^'[^']+' failed:\s*/, "") : undefined;
        if (i >= 0) events[i] = { ...events[i], status: failed ? "failed" : "completed", detail: text, durationMs };
        break;
      }
      case "memory_retrieved":
      case "memory_restored":
      case "memory_saved":
        add({ name: "Memory", kind: "memory", status: "completed", detail });
        break;
      case "error":
      case "limit_reached":
        add({ name: stage === "error" ? "Error" : "Limit reached", kind: "error", status: "failed", detail });
        break;
    }
  }
  return events;
}

/** 240ms, 1.4s, 12s, 1m 05s. */
export function formatDuration(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)}ms`;
  if (ms < 10_000) return `${(ms / 1000).toFixed(1)}s`;
  const seconds = Math.round(ms / 1000);
  if (seconds < 60) return `${seconds}s`;
  return `${Math.floor(seconds / 60)}m ${String(seconds % 60).padStart(2, "0")}s`;
}
