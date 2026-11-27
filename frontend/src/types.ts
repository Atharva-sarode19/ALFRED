export type AlfredState =
  | "idle"
  | "listening"
  | "processing"
  | "thinking"
  | "executing"
  | "speaking"
  | "error";

export interface TraceStep {
  stage: string;
  detail: string;
  /** Measured by the backend; only present on `tool_result` steps. */
  duration_ms?: number | null;
}

export interface PendingConfirmation {
  tool_name: string;
  arguments: Record<string, unknown>;
  call_id: string;
  /** Speakable summary of the action, e.g. "I can save that note". */
  description?: string;
}

export interface ChatResponse {
  session_id: string;
  response: string;
  trace: TraceStep[];
  pending_confirmation: PendingConfirmation | null;
  iterations_used: number;
}

export type LedgerRole = "user" | "alfred" | "system";

export interface LedgerEntry {
  id: string;
  role: LedgerRole;
  text: string;
}

export interface FileInfo {
  id: string;
  name: string;
  media_type: string;
  size_bytes: number;
  char_count: number;
  uploaded_at: string;
}

export interface Reminder {
  id: number;
  title: string;
  notes: string | null;
  due_local: string;
  due_utc: string;
  timezone: string;
}

export type ActivityStatus = "pending" | "running" | "completed" | "failed" | "waiting";
export type ActivityApproval = "required" | "approved" | "declined";

/** One row in the Agent Activity panel, derived only from real backend trace steps. */
export interface ActivityEvent {
  id: string;
  /** Tool name for tool events, or a short label for memory/error events. */
  name: string;
  kind: "tool" | "memory" | "error";
  status: ActivityStatus;
  approval?: ActivityApproval;
  detail?: string;
  /** Measured tool execution time (backend), when reported. */
  durationMs?: number;
}

export interface MemoryStatus {
  enabled: boolean;
  configured?: boolean;
  connected?: boolean;
  detail?: string;
  memories?: Record<string, number>;
}
