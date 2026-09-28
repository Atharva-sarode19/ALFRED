import type { ChatResponse } from "../types";
import { stripMarkdown } from "../utils/markdown";

const configuredApiBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim();
const API_BASE_URL = (configuredApiBaseUrl || "http://127.0.0.1:8001").replace(/\/+$/, "");

console.info("[ALFRED] API base URL:", API_BASE_URL);

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
  autoApproveConfirmations = false
): Promise<ChatResponse> {
  const url = `${API_BASE_URL}/api/chat`;
  const body = {
    message,
    session_id: sessionId,
    auto_approve_confirmations: autoApproveConfirmations,
  };
  console.info("[ALFRED] /api/chat request URL:", url);
  console.info("[ALFRED] /api/chat request body:", body);

  let response: Response;
  try {
    response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch (error) {
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

export async function transcribeAudio(blob: Blob): Promise<string> {
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
    response = await fetch(url, { method: "POST", body: form });
  } catch (error) {
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

export async function synthesizeSpeech(text: string): Promise<Blob> {
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
    });
  } catch (error) {
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
