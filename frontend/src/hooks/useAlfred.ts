import { useCallback, useEffect, useRef, useState } from "react";
import {
  ApiError,
  cancelPending,
  confirmAction,
  isAbortError,
  sendChatMessage,
  synthesizeSpeech,
  transcribeAudio,
} from "../services/api";
import type { OrbController } from "../orb/orbController";
import type { AlfredState, ChatResponse, LedgerEntry, PendingConfirmation, TraceStep } from "../types";
import { runningAudioContext, startMeter, type LevelMeter } from "../utils/audioLevel";
import { useVoiceRecorder } from "./useVoiceRecorder";

let entryCounter = 0;
function nextId(): string {
  entryCounter += 1;
  return `entry-${entryCounter}`;
}

interface ListenOptions {
  /** Silence ends the recording (hands-free). Default true. */
  auto?: boolean;
  /** Listening for a yes/no: wait a little longer before giving up. */
  confirmation?: boolean;
}

/**
 * The conversation state machine: idle -> listening -> processing -> thinking ->
 * executing -> speaking -> idle. Everything that can interrupt it (key,
 * orb press) goes through `cancelInteraction`, which stops the microphone, the
 * speaker and any request in flight. `turnRef` invalidates stale async work.
 */
export function useAlfred(controller: OrbController) {
  const [state, setState] = useState<AlfredState>("idle");
  const [ledger, setLedger] = useState<LedgerEntry[]>([]);
  const [trace, setTrace] = useState<TraceStep[]>([]);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [pendingConfirmation, setPendingConfirmation] = useState<PendingConfirmation | null>(null);
  // Bumped after every agent turn so the workspace panel reloads files and reminders.
  const [refreshKey, setRefreshKey] = useState(0);

  const sessionIdRef = useRef<string | null>(null);
  const turnRef = useRef(0);
  const abortRef = useRef<AbortController | null>(null);
  const stopSpeakingRef = useRef<(() => void) | null>(null);
  const pendingRef = useRef<PendingConfirmation | null>(null);
  const finishListeningRef = useRef<() => Promise<void>>(async () => {});
  const recorder = useVoiceRecorder();

  useEffect(() => {
    pendingRef.current = pendingConfirmation;
  }, [pendingConfirmation]);

  const appendLedger = useCallback((role: LedgerEntry["role"], text: string) => {
    setLedger((prev) => [...prev, { id: nextId(), role, text }]);
  }, []);

  /** Start a new unit of work; anything still running from before is cancelled. */
  const beginTurn = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = new AbortController();
    turnRef.current += 1;
    return { turn: turnRef.current, signal: abortRef.current.signal };
  }, []);

  const speak = useCallback(
    async (text: string, turn: number, signal: AbortSignal): Promise<boolean> => {
      setState("speaking");
      let audioUrl: string | null = null;
      let meter: LevelMeter | null = null;
      let failed = false;
      try {
        const audioBlob = await synthesizeSpeech(text, signal);
        if (turn !== turnRef.current) return false;
        audioUrl = URL.createObjectURL(audioBlob);
        const audio = new Audio(audioUrl);

        // Drive the orb from the actual speech amplitude. Only route the audio through
        // Web Audio if the context is running, otherwise the element would go silent.
        try {
          const context = await runningAudioContext();
          if (context) {
            const source = context.createMediaElementSource(audio);
            meter = startMeter(context, source, (rms) => controller.setLevel(Math.min(1, rms * 4)), 40, true);
          }
        } catch (meterError) {
          console.warn("[ALFRED] Speech level meter unavailable; playing without it:", meterError);
        }

        await new Promise<void>((resolve, reject) => {
          stopSpeakingRef.current = () => {
            audio.pause();
            resolve();
          };
          audio.onended = () => resolve();
          audio.onerror = () => reject(new Error("The browser could not play the synthesized audio."));
          audio.play().catch(reject);
        });
      } catch (error) {
        if (isAbortError(error)) return false;
        failed = true;
        const detail = error instanceof Error ? error.message : String(error);
        console.error("[ALFRED] Speech synthesis or playback failed:", error);
        setErrorMessage(`Speech playback failed: ${detail}`);
      } finally {
        meter?.stop();
        controller.setLevel(0);
        stopSpeakingRef.current = null;
        if (audioUrl) URL.revokeObjectURL(audioUrl);
      }
      if (failed) {
        setState("error");
        return false;
      }
      return turn === turnRef.current;
    },
    [controller]
  );

  const startListening = useCallback(
    async (options: ListenOptions = {}) => {
      const { auto = true, confirmation = false } = options;
      setErrorMessage(null);
      const failure = await recorder.start({
        onLevel: (level) => controller.setLevel(level),
        autoStop: auto
          ? {
              noSpeechMs: confirmation ? 8000 : 6000,
              onSilence: () => void finishListeningRef.current(),
              // Nobody spoke: discard the recording. Silence is never an answer.
              onNoSpeech: () => {
                recorder.cancel();
                controller.setLevel(0);
                setState("idle");
              },
            }
          : undefined,
      });
      if (failure) {
        setErrorMessage(failure);
        appendLedger("system", `Error: ${failure}`);
        setState("error");
        return;
      }
      setState("listening");
    },
    [appendLedger, controller, recorder]
  );

  /** Shared by normal turns and confirmation answers. */
  const handleResult = useCallback(
    async (result: ChatResponse, voice: boolean, turn: number, signal: AbortSignal) => {
      sessionIdRef.current = result.session_id;
      setTrace(result.trace);
      setRefreshKey((key) => key + 1);

      setState("executing");

      const agentError = result.trace.find((step) => step.stage === "error");
      if (agentError) {
        setPendingConfirmation(null);
        appendLedger("alfred", result.response);
        setErrorMessage(`Backend reported an agent error: ${agentError.detail}`);
        setState("error");
        return;
      }

      setPendingConfirmation(result.pending_confirmation);
      appendLedger("alfred", result.response);
      const spoken = await speak(result.response, turn, signal);
      if (!spoken) return; // cancelled, or speech failed (state already set)

      if (result.pending_confirmation && voice) {
        // ALFRED asked "Shall I go ahead, Sir?" aloud: listen for the answer.
        await startListening({ auto: true, confirmation: true });
        return;
      }
      setState("idle");
    },
    [appendLedger, speak, startListening]
  );

  const reportError = useCallback(
    (err: unknown, fallback: string) => {
      const detail = err instanceof Error ? err.message : fallback;
      console.error("[ALFRED] Chat turn failed:", err);
      setErrorMessage(detail);
      appendLedger("system", `Error: ${detail}`);
      setState("error");
    },
    [appendLedger]
  );

  const runTurn = useCallback(
    async (message: string, voice: boolean) => {
      const { turn, signal } = beginTurn();
      setState("thinking");
      try {
        const result = await sendChatMessage(message, sessionIdRef.current, signal);
        if (turn !== turnRef.current) return;
        await handleResult(result, voice, turn, signal);
      } catch (err) {
        if (isAbortError(err) || turn !== turnRef.current) return;
        reportError(err, "Something went wrong.");
      }
    },
    [beginTurn, handleResult, reportError]
  );

  const answerPending = useCallback(
    async (approve: boolean) => {
      const sessionId = sessionIdRef.current;
      if (!sessionId || !pendingRef.current) return;
      const { turn, signal } = beginTurn();
      setPendingConfirmation(null);
      setState("thinking");
      try {
        const result = await confirmAction(sessionId, approve, signal);
        if (turn !== turnRef.current) return;
        await handleResult(result, false, turn, signal);
      } catch (err) {
        if (isAbortError(err) || turn !== turnRef.current) return;
        reportError(err, "Something went wrong.");
      }
    },
    [beginTurn, handleResult, reportError]
  );

  const stopListeningAndSend = useCallback(async () => {
    const blob = await recorder.stop();
    controller.setLevel(0);
    if (!blob) {
      setState("idle");
      return;
    }

    setState("processing");
    const { turn, signal } = beginTurn();
    try {
      const text = await transcribeAudio(blob, signal);
      if (turn !== turnRef.current) return;
      console.info("[ALFRED] Sending STT result to /api/chat:", text);
      appendLedger("user", text);
      await runTurn(text, true);
    } catch (err) {
      if (isAbortError(err) || turn !== turnRef.current) return;
      if (err instanceof ApiError && err.status === 422) {
        // "No speech detected": a false trigger or a cough, not an error worth a banner.
        setState("idle");
        return;
      }
      reportError(err, "Transcription failed.");
    }
  }, [appendLedger, beginTurn, controller, recorder, reportError, runTurn]);

  useEffect(() => {
    finishListeningRef.current = stopListeningAndSend;
  }, [stopListeningAndSend]);

  /**
   * Stop whatever is happening: microphone, speech playback and requests in flight.
   * A pending confirmation is dropped (declined) -- cancelling can never approve anything.
   * Returns true if there was something to cancel.
   */
  const cancelInteraction = useCallback((): boolean => {
    const hadPending = pendingRef.current !== null;
    const wasBusy = state !== "idle";
    if (!hadPending && !wasBusy) return false;

    turnRef.current += 1;
    abortRef.current?.abort();
    abortRef.current = null;
    recorder.cancel();
    stopSpeakingRef.current?.();
    controller.setLevel(0);

    if (hadPending) {
      const sessionId = sessionIdRef.current;
      setPendingConfirmation(null);
      appendLedger("system", "Cancelled. Nothing was changed.");
      if (sessionId) void cancelPending(sessionId).catch(() => {});
    }
    setErrorMessage(null);
    setState("idle");
    return true;
  }, [appendLedger, controller, recorder, state]);

  const sendTextMessage = useCallback(
    async (message: string) => {
      if (!message.trim()) return;
      appendLedger("user", message);
      await runTurn(message, false);
    },
    [appendLedger, runTurn]
  );

  const confirmPendingTool = useCallback(() => answerPending(true), [answerPending]);
  const declinePendingTool = useCallback(() => answerPending(false), [answerPending]);

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
    refreshKey,
    startListening,
    stopListeningAndSend,
    cancelInteraction,
    sendTextMessage,
    confirmPendingTool,
    declinePendingTool,
    dismissError,
  };
}
