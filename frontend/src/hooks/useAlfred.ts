import { useCallback, useRef, useState } from "react";
import { sendChatMessage, synthesizeSpeech, transcribeAudio } from "../services/api";
import type { AlfredState, LedgerEntry, PendingConfirmation, TraceStep } from "../types";
import { useVoiceRecorder } from "./useVoiceRecorder";

let entryCounter = 0;
function nextId(): string {
  entryCounter += 1;
  return `entry-${entryCounter}`;
}

export function useAlfred() {
  const [state, setState] = useState<AlfredState>("idle");
  const [ledger, setLedger] = useState<LedgerEntry[]>([]);
  const [trace, setTrace] = useState<TraceStep[]>([]);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [pendingConfirmation, setPendingConfirmation] = useState<PendingConfirmation | null>(null);

  const sessionIdRef = useRef<string | null>(null);
  const recorder = useVoiceRecorder();

  const appendLedger = useCallback((role: LedgerEntry["role"], text: string) => {
    setLedger((prev) => [...prev, { id: nextId(), role, text }]);
  }, []);

  const speak = useCallback(async (text: string) => {
    setState("speaking");
    let audioUrl: string | null = null;
    let playbackFailed = false;
    try {
      const audioBlob = await synthesizeSpeech(text);
      audioUrl = URL.createObjectURL(audioBlob);
      const audio = new Audio(audioUrl);
      await new Promise<void>((resolve, reject) => {
        audio.onended = () => resolve();
        audio.onerror = () => reject(new Error("The browser could not play the synthesized audio."));
        audio.play().catch(reject);
      });
    } catch (error) {
      playbackFailed = true;
      const detail = error instanceof Error ? error.message : String(error);
      console.error("[ALFRED] Speech synthesis or playback failed:", error);
      setErrorMessage(`Speech playback failed: ${detail}`);
    } finally {
      if (audioUrl) URL.revokeObjectURL(audioUrl);
    }
    setState(playbackFailed ? "error" : "idle");
  }, []);

  const runTurn = useCallback(
    async (message: string, autoApprove = false) => {
      setState("thinking");
      try {
        const result = await sendChatMessage(message, sessionIdRef.current, autoApprove);
        sessionIdRef.current = result.session_id;
        setTrace(result.trace);

        setState("executing");

        const agentError = result.trace.find((step) => step.stage === "error");
        if (agentError) {
          appendLedger("alfred", result.response);
          setErrorMessage(`Backend reported an agent error: ${agentError.detail}`);
          setState("error");
          return;
        }

        if (result.pending_confirmation) {
          setPendingConfirmation(result.pending_confirmation);
          appendLedger("alfred", result.response);
          setState("idle");
          return;
        }

        setPendingConfirmation(null);
        appendLedger("alfred", result.response);
        await speak(result.response);
      } catch (err) {
        const detail = err instanceof Error ? err.message : "Something went wrong.";
        console.error("[ALFRED] Chat turn failed:", err);
        setErrorMessage(detail);
        appendLedger("system", `Error: ${detail}`);
        setState("error");
      }
    },
    [appendLedger, speak]
  );

  const startListening = useCallback(async () => {
    setErrorMessage(null);
    await recorder.start();
    setState("listening");
  }, [recorder]);

  const stopListeningAndSend = useCallback(async () => {
    const blob = await recorder.stop();
    if (!blob) {
      setState("idle");
      return;
    }

    setState("processing");
    try {
      const text = await transcribeAudio(blob);
      console.info("[ALFRED] Sending STT result to /api/chat:", text);
      appendLedger("user", text);
      await runTurn(text);
    } catch (err) {
      const detail = err instanceof Error ? err.message : "Transcription failed.";
      setErrorMessage(detail);
      appendLedger("system", `Error: ${detail}`);
      setState("error");
    }
  }, [appendLedger, recorder, runTurn]);

  const sendTextMessage = useCallback(
    async (message: string) => {
      if (!message.trim()) return;
      appendLedger("user", message);
      await runTurn(message);
    },
    [appendLedger, runTurn]
  );

  const confirmPendingTool = useCallback(async () => {
    if (!pendingConfirmation) return;
    const lastUserEntry = [...ledger].reverse().find((entry) => entry.role === "user");
    setPendingConfirmation(null);
    if (lastUserEntry) {
      await runTurn(lastUserEntry.text, true);
    }
  }, [ledger, pendingConfirmation, runTurn]);

  const declinePendingTool = useCallback(() => {
    setPendingConfirmation(null);
    appendLedger("system", "Okay, I won't run that.");
  }, [appendLedger]);

  const dismissError = useCallback(() => {
    setErrorMessage(null);
    setState("idle");
  }, []);

  return {
    state,
    ledger,
    trace,
    errorMessage,
    pendingConfirmation,
    startListening,
    stopListeningAndSend,
    sendTextMessage,
    confirmPendingTool,
    declinePendingTool,
    dismissError,
  };
}
