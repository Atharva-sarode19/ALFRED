import { useCallback, useRef, useState } from "react";

export type RecorderStatus = "idle" | "recording" | "error";

/**
 * Push-to-talk microphone capture.
 *
 * ALFRED's wake-word engine is a future capability (see WakeWordDetector on
 * the backend's roadmap) -- Phase 2 implements push-to-talk, as the spec
 * directs when a true wake-word engine isn't practical yet.
 */
export function useVoiceRecorder() {
  const [status, setStatus] = useState<RecorderStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);

  const start = useCallback(async () => {
    setError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      chunksRef.current = [];

      const recorder = new MediaRecorder(stream);
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      };
      mediaRecorderRef.current = recorder;
      recorder.start();
      setStatus("recording");
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Microphone access was denied or unavailable.";
      setError(message);
      setStatus("error");
    }
  }, []);

  const stop = useCallback((): Promise<Blob | null> => {
    return new Promise((resolve) => {
      const recorder = mediaRecorderRef.current;
      if (!recorder || recorder.state === "inactive") {
        resolve(null);
        return;
      }

      recorder.onstop = () => {
        const mimeType = recorder.mimeType || chunksRef.current[0]?.type || "audio/webm";
        const blob = new Blob(chunksRef.current, { type: mimeType });
        streamRef.current?.getTracks().forEach((track) => track.stop());
        streamRef.current = null;
        setStatus("idle");
        resolve(blob.size > 0 ? blob : null);
      };
      recorder.stop();
    });
  }, []);

  return { status, error, start, stop };
}
