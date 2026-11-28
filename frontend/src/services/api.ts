import type { ChatResponse, FileInfo, MemoryStatus, Reminder, Workflow } from "../types";
import { stripMarkdown } from "../utils/markdown";

const configuredApiBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim();
export const API_BASE_URL = (configuredApiBaseUrl || "http://127.0.0.1:8001").replace(/\/+$/, "");

console.info("[ALFRED] API base URL:", API_BASE_URL);

export function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

export class ApiError extends Error {
  constructor(message: string, public status: number) {
    super(message);
    this.name = "ApiError";
  }
}

async function readErrorDetail(response: Response): Promise<string> {
  try {
    const body = await response.json();
    return body?.detail ?? response.statusText;
  } catch {
    return response.statusText;
  }
}

export async function sendChatMessage(
  message: string,
  sessionId: string | null,
  signal?: AbortSignal
): Promise<ChatResponse> {
  const url = `${API_BASE_URL}/api/chat`;
  const body = {
    message,
    session_id: sessionId,
  };
  console.info("[ALFRED] /api/chat request URL:", url);
  console.info("[ALFRED] /api/chat request body:", body);

  let response: Response;
  try {
    response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal,
    });
  } catch (error) {
    if (isAbortError(error)) throw error;
    console.error("[ALFRED] /api/chat network/CORS request failed:", { url, error });
    throw new ApiError(
      `Could not reach ${url}. Check the frontend API URL, backend status, and CORS settings. ${error instanceof Error ? error.message : String(error)}`,
      0
    );
  }

  console.info("[ALFRED] /api/chat status:", response.status);
  const data = await response.json();
  console.info("[ALFRED] /api/chat response:", data);
  const agentErrors = Array.isArray(data?.trace)
    ? data.trace.filter((step: { stage?: string }) => step?.stage === "error")
    : [];
  if (agentErrors.length > 0) {
    console.error("[ALFRED] /api/chat returned HTTP success with an agent error:", {
      response: data.response,
      trace: agentErrors,
    });
  }

  if (!response.ok) {
    const detail = data?.detail ?? response.statusText;
    throw new ApiError(
      typeof detail === "string" ? detail : JSON.stringify(detail),
      response.status
    );
  }
  if (typeof data?.response !== "string") {
    throw new ApiError("The chat API returned HTTP success without a response field.", response.status);
  }

  return data as ChatResponse;
}

export async function transcribeAudio(blob: Blob, signal?: AbortSignal): Promise<string> {
  const url = `${API_BASE_URL}/api/voice/transcribe`;
  const form = new FormData();
  const mimeType = blob.type.split(";")[0].toLowerCase();
  const extensionByMimeType: Record<string, string> = {
    "audio/webm": "webm",
    "audio/mp4": "m4a",
    "audio/ogg": "ogg",
    "audio/wav": "wav",
    "audio/mpeg": "mp3",
  };
  const extension = extensionByMimeType[mimeType] ?? "webm";
  const fileName = `recording.${extension}`;
  form.append("audio", blob, fileName);
  console.info("[ALFRED] STT request:", {
    url,
    fileName,
    mimeType: blob.type || "unknown",
    bytes: blob.size,
  });

  let response: Response;
  try {
    response = await fetch(url, { method: "POST", body: form, signal });
  } catch (error) {
    if (isAbortError(error)) throw error;
    console.error("[ALFRED] STT network/CORS request failed:", { url, error });
    throw new ApiError(
      `Could not reach ${url}. Check the frontend API URL, backend status, and CORS settings. ${error instanceof Error ? error.message : String(error)}`,
      0
    );
  }
  console.info("[ALFRED] STT status:", response.status);
  const data = await response.json();
  if (!response.ok) {
    const detail = data?.detail ?? response.statusText;
    throw new ApiError(
      typeof detail === "string" ? detail : JSON.stringify(detail),
      response.status
    );
  }

  const text = data?.text;
  if (typeof text !== "string") {
    throw new ApiError("The transcription API returned HTTP success without a text field.", response.status);
  }
  console.info("[ALFRED] STT result:", text);
  return text;
}

export async function synthesizeSpeech(text: string, signal?: AbortSignal): Promise<Blob> {
  const spokenText = stripMarkdown(text);
  const url = `${API_BASE_URL}/api/voice/synthesize`;
  const body = { text: spokenText };
  console.info("[ALFRED] TTS request:", { url, body });

  let response: Response;
  try {
    response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal,
    });
  } catch (error) {
    if (isAbortError(error)) throw error;
    console.error("[ALFRED] TTS network/CORS request failed:", { url, error });
    throw new ApiError(
      `Could not reach ${url}. Check the frontend API URL, backend status, and CORS settings. ${error instanceof Error ? error.message : String(error)}`,
      0
    );
  }
  console.info("[ALFRED] TTS status:", response.status);
  if (!response.ok) {
    throw new ApiError(await readErrorDetail(response), response.status);
  }
  const audio = await response.blob();
  console.info("[ALFRED] TTS audio response:", {
    contentType: audio.type,
    bytes: audio.size,
  });
  return audio;
}

/** fetch + JSON for the Phase 3 endpoints, with the same error shape as the calls above. */
async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${API_BASE_URL}${path}`;
  let response: Response;
  try {
    response = await fetch(url, init);
  } catch (error) {
    if (isAbortError(error)) throw error;
    console.error(`[ALFRED] ${path} network/CORS request failed:`, { url, error });
    throw new ApiError(
      `Could not reach ${url}. Check the frontend API URL, backend status, and CORS settings. ${error instanceof Error ? error.message : String(error)}`,
      0
    );
  }
  if (!response.ok) {
    throw new ApiError(await readErrorDetail(response), response.status);
  }
  return (await response.json()) as T;
}

/**
 * Answer the action the server is waiting on. The server runs (or declines)
 * exactly the call it stored -- the client cannot pre-approve anything.
 */
export function confirmAction(sessionId: string, approve: boolean, signal?: AbortSignal): Promise<ChatResponse> {
  return requestJson<ChatResponse>("/api/chat/confirm", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, approve }),
    signal,
  });
}

/** Drop the action waiting for confirmation without running it (silent: no model call). */
export function cancelPending(sessionId: string): Promise<{ cancelled: boolean }> {
  return requestJson<{ cancelled: boolean }>("/api/chat/cancel", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId }),
  });
}

export function uploadFile(file: File): Promise<FileInfo> {
  const form = new FormData();
  form.append("file", file);
  return requestJson<FileInfo>("/api/files/upload", { method: "POST", body: form });
}

export function listFiles(): Promise<FileInfo[]> {
  return requestJson<FileInfo[]>("/api/files");
}

export function listReminders(): Promise<Reminder[]> {
  return requestJson<Reminder[]>("/api/reminders?scope=upcoming");
}

export function getMemoryStatus(signal?: AbortSignal): Promise<MemoryStatus> {
  return requestJson<MemoryStatus>("/api/memory/status", { signal });
}

export async function deleteFile(fileId: string): Promise<void> {
  const url = `${API_BASE_URL}/api/files/${encodeURIComponent(fileId)}`;
  let response: Response;
  try {
    response = await fetch(url, { method: "DELETE" });
  } catch (error) {
    throw new ApiError(`Could not reach the server to remove the document. ${error instanceof Error ? error.message : ""}`.trim(), 0);
  }
  if (!response.ok) throw new ApiError(await readErrorDetail(response), response.status);
}

// ---- Phase 5: workflows ------------------------------------------------------------------
const JSON_HEADERS = { "Content-Type": "application/json" };

export function listWorkflows(signal?: AbortSignal): Promise<Workflow[]> {
  return requestJson<Workflow[]>("/api/workflows?limit=10", { signal });
}

export function getWorkflow(id: string, signal?: AbortSignal): Promise<Workflow> {
  return requestJson<Workflow>(`/api/workflows/${encodeURIComponent(id)}`, { signal });
}

function workflowAction(id: string, action: string, body: Record<string, unknown> = {}): Promise<Workflow> {
  return requestJson<Workflow>(`/api/workflows/${encodeURIComponent(id)}/${action}`, {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify(body),
  });
}

/** Approve or reject exactly the call shown to the user (`callId` guards against a stale view). */
export function answerWorkflowApproval(id: string, approve: boolean, taskId: string, callId: string): Promise<Workflow> {
  return workflowAction(id, approve ? "approve" : "reject", { task_id: taskId, call_id: callId });
}

export function cancelWorkflow(id: string): Promise<Workflow> {
  return workflowAction(id, "cancel");
}

export function resumeWorkflow(id: string, retryFailed = false): Promise<Workflow> {
  return workflowAction(id, "resume", { retry_failed: retryFailed });
}
