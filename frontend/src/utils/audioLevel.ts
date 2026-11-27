/**
 * One shared AudioContext plus small loudness meters.
 *
 * Browsers cap how many AudioContexts a page may create, and a suspended
 * context (autoplay policy) is a trap: routing an <audio> element through one
 * that never resumes makes the element silent. `runningAudioContext()` therefore
 * only hands out a context that is actually running; callers fall back to
 * plain playback or to no meter when it returns null.
 */

let sharedContext: AudioContext | null = null;

type AudioContextCtor = typeof AudioContext;

export function getAudioContext(): AudioContext | null {
  if (typeof window === "undefined") return null;
  const Ctor: AudioContextCtor | undefined =
    window.AudioContext ?? (window as unknown as { webkitAudioContext?: AudioContextCtor }).webkitAudioContext;
  if (!Ctor) return null;
  if (!sharedContext || sharedContext.state === "closed") sharedContext = new Ctor();
  return sharedContext;
}

export async function runningAudioContext(): Promise<AudioContext | null> {
  const context = getAudioContext();
  if (!context) return null;
  if (context.state === "suspended") {
    try {
      await context.resume();
    } catch {
      /* needs a user gesture; handled by the state check below */
    }
  }
  return context.state === "running" ? context : null;
}

/** Root-mean-square loudness of a time-domain buffer (0..1). */
export function rmsOf(samples: ArrayLike<number>): number {
  if (samples.length === 0) return 0;
  let sum = 0;
  for (let i = 0; i < samples.length; i++) sum += samples[i] * samples[i];
  return Math.sqrt(sum / samples.length);
}

export interface LevelMeter {
  stop(): void;
}

/**
 * Report the RMS level of `source` every `intervalMs`.
 * With `passThrough` the audio is also connected to the speakers (required for
 * <audio> elements, which would otherwise go silent); microphones must NOT be
 * passed through or the user would hear themselves.
 */
export function startMeter(
  context: AudioContext,
  source: AudioNode,
  onLevel: (rms: number) => void,
  intervalMs: number,
  passThrough: boolean
): LevelMeter {
  const analyser = context.createAnalyser();
  analyser.fftSize = 1024;
  source.connect(analyser);
  if (passThrough) analyser.connect(context.destination);

  const buffer = new Float32Array(analyser.fftSize);
  const timer = window.setInterval(() => {
    analyser.getFloatTimeDomainData(buffer);
    onLevel(rmsOf(buffer));
  }, intervalMs);

  return {
    stop() {
      window.clearInterval(timer);
      try {
        source.disconnect(analyser);
        analyser.disconnect();
      } catch {
        /* already disconnected */
      }
    },
  };
}
