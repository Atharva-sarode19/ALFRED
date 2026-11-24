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
