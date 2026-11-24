/**
 * Wake-word detector interface (Section 12 of the spec).
 *
 * This is a STUB. It does not listen for "Hey ALFRED" yet — it exists so
 * the rest of the app can be wired against a stable interface now, and a
 * real engine (Picovoice Porcupine, generating a custom "Hey ALFRED"
 * keyword model via their console + Web SDK) can be dropped in later
 * without touching App.tsx or useAlfred.ts again.
 *
 * Swap-in plan: replace the body of `useWakeWord` with Porcupine's
 * `usePorcupine` hook (or a thin wrapper around their Web SDK), keeping
 * the same `{ isArmed, arm, disarm }` shape so nothing else needs to change.
 */
import { useCallback, useState } from "react";

interface UseWakeWordOptions {
  /** Called when the wake phrase is detected. Not invoked by this stub. */
  onWake: () => void;
}

interface UseWakeWordResult {
  /** Whether wake-word listening is conceptually "on". Always false until a real engine is wired in. */
  isArmed: boolean;
  /** No-op until a real detector is wired in. */
  arm: () => void;
  /** No-op until a real detector is wired in. */
  disarm: () => void;
  /** True for this stub — lets the UI say "coming soon" instead of pretending it works. */
  isStub: true;
}

export function useWakeWord(_options: UseWakeWordOptions): UseWakeWordResult {
  const [isArmed, setIsArmed] = useState(false);

  const arm = useCallback(() => {
    // TODO(wake-word): initialize Porcupine here with a "Hey ALFRED" keyword
    // model, start streaming mic audio to it, and call onWake() on detection.
    setIsArmed(false);
  }, []);

  const disarm = useCallback(() => setIsArmed(false), []);

  return { isArmed, arm, disarm, isStub: true };
}
