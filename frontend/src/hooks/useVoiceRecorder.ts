import { useCallback, useEffect, useRef, useState } from "react";
import { runningAudioContext, startMeter, type LevelMeter } from "../utils/audioLevel";
import { SilenceDetector } from "../utils/silenceDetector";

export type RecorderStatus = "idle" | "recording" | "error";

export interface RecorderStartOptions {
  /** Microphone loudness 0..1 while recording (drives the orb). */
  onLevel?: (level: number) => void;
  /**
   * Hands-free mode: end the recording on silence.
   * `onSilence` fires once the user spoke and went quiet; `onNoSpeech` fires if
   * nobody spoke (nothing should be sent in that case).
   */
  autoStop?: { onSilence: () => void; onNoSpeech: () => void; noSpeechMs?: number };
}

/** Fallback cap when no audio meter is available (e.g. the browser blocked the AudioContext). */
const BLIND_RECORDING_MS = 12000;

function describeMicError(err: unknown): string {
  if (err instanceof DOMException) {
    if (err.name === "NotAllowedError") return "Microphone permission was denied. Allow it in the browser's site settings.";
    if (err.name === "NotFoundError") return "No microphone was found.";
    if (err.name === "NotReadableError") return "The microphone is in use by another application.";
  }
  return err instanceof Error ? err.message : "Microphone access was denied or unavailable.";
}

/**
 * Microphone capture for one command: push-to-talk or hands-free (silence ends it).
 * The microphone is released as soon as a recording ends or is cancelled.
 */
export function useVoiceRecorder() {
  const [status, setStatus] = useState<RecorderStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const meterRef = useRef<LevelMeter | null>(null);
  const blindTimerRef = useRef<number | null>(null);

  const releaseResources = useCallback(() => {
    meterRef.current?.stop();
    meterRef.current = null;
    if (blindTimerRef.current !== null) {
      window.clearTimeout(blindTimerRef.current);
      blindTimerRef.current = null;
    }
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
  }, []);

  /** Returns null on success or a human-readable error message. */
  const start = useCallback(
    async (options: RecorderStartOptions = {}): Promise<string | null> => {
      setError(null);
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") return null; // already recording
      if (!navigator.mediaDevices?.getUserMedia) {
        const message = "This browser cannot access the microphone.";
        setError(message);
        setStatus("error");
        return message;
      }

      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
        });
        streamRef.current = stream;
        chunksRef.current = [];

        const recorder = new MediaRecorder(stream);
        recorder.ondataavailable = (event) => {
          if (event.data.size > 0) chunksRef.current.push(event.data);
        };
        mediaRecorderRef.current = recorder;
        recorder.start();
        setStatus("recording");

        const { onLevel, autoStop } = options;
        const context = onLevel || autoStop ? await runningAudioContext() : null;
        if (context && mediaRecorderRef.current === recorder) {
          const detector = autoStop ? new SilenceDetector({ noSpeechMs: autoStop.noSpeechMs }) : null;
          let finished = false;
          const source = context.createMediaStreamSource(stream);
          meterRef.current = startMeter(context, source, (rms) => {
            onLevel?.(Math.min(1, rms * 5));
            if (!detector || !autoStop || finished) return;
            const verdict = detector.push(rms, performance.now());
            if (verdict === "continue") return;
            finished = true;
            if (verdict === "stop") autoStop.onSilence();
            else autoStop.onNoSpeech();
          }, 50, false);
        } else if (autoStop) {
          // No meter available: end the recording after a fixed time rather than never.
          blindTimerRef.current = window.setTimeout(autoStop.onSilence, BLIND_RECORDING_MS);
        }
        return null;
      } catch (err) {
        releaseResources();
        const message = describeMicError(err);
        setError(message);
        setStatus("error");
        return message;
      }
    },
    [releaseResources]
  );

  const stop = useCallback((): Promise<Blob | null> => {
    return new Promise((resolve) => {
      const recorder = mediaRecorderRef.current;
      if (!recorder || recorder.state === "inactive") {
        releaseResources();
        resolve(null);
        return;
      }

      recorder.onstop = () => {
        const mimeType = recorder.mimeType || chunksRef.current[0]?.type || "audio/webm";
        const blob = new Blob(chunksRef.current, { type: mimeType });
        releaseResources();
        mediaRecorderRef.current = null;
        setStatus("idle");
        resolve(blob.size > 0 ? blob : null);
      };
      recorder.stop();
    });
  }, [releaseResources]);

  /** Stop and throw the recording away (nothing is transcribed or sent). */
  const cancel = useCallback(() => {
    const recorder = mediaRecorderRef.current;
    mediaRecorderRef.current = null;
    if (recorder && recorder.state !== "inactive") {
      recorder.onstop = null;
      recorder.stop();
    }
    chunksRef.current = [];
    releaseResources();
    setStatus("idle");
  }, [releaseResources]);

  // Never leave the microphone open if the component goes away mid-recording.
  useEffect(() => cancel, [cancel]);

  return { status, error, start, stop, cancel };
}
