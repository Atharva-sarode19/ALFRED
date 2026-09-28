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
