/**
 * Decides when a hands-free recording should end.
 *
 * Feed it the microphone's RMS level (0..1) with a timestamp. It answers:
 *   "continue" - keep recording,
 *   "stop"     - the user spoke and then went quiet (or hit the time cap): send it,
 *   "abort"    - nobody spoke at all: discard it, do not send anything.
 *
 * The first moments are used to estimate the room's noise floor so a noisy
 * room does not keep the recording open forever. Silence is never treated as
 * consent to anything -- an "abort" sends nothing.
 */

export type SilenceVerdict = "continue" | "stop" | "abort";

export interface SilenceOptions {
  calibrationMs: number;
  minSpeechMs: number;
  silenceMs: number;
  noSpeechMs: number;
  maxMs: number;
  minThreshold: number;
  maxThreshold: number;
}

export const DEFAULT_SILENCE_OPTIONS: SilenceOptions = {
  calibrationMs: 300,
  minSpeechMs: 120,
  silenceMs: 1100,
  noSpeechMs: 6000,
  maxMs: 20000,
  minThreshold: 0.02,
  maxThreshold: 0.06,
};

export class SilenceDetector {
  private readonly opts: SilenceOptions;
  private startMs: number | null = null;
  private floor = Infinity;
  private threshold = 0;
  private speaking = false;
  private aboveSinceMs: number | null = null;
  private lastVoiceMs = 0;

  constructor(options: Partial<SilenceOptions> = {}) {
    this.opts = { ...DEFAULT_SILENCE_OPTIONS, ...options };
  }

  push(level: number, nowMs: number): SilenceVerdict {
    if (this.startMs === null) this.startMs = nowMs;
    const elapsed = nowMs - this.startMs;

    if (elapsed < this.opts.calibrationMs) {
      // The quietest sample seen so far approximates the room, even if the
      // user is already talking over part of this window.
      this.floor = Math.min(this.floor, level);
      return "continue";
    }
    if (this.threshold === 0) {
      const floor = Number.isFinite(this.floor) ? this.floor : 0;
      this.threshold = Math.min(this.opts.maxThreshold, Math.max(this.opts.minThreshold, floor * 3 + 0.008));
    }

    if (level > this.threshold) {
      if (this.aboveSinceMs === null) this.aboveSinceMs = nowMs;
      if (!this.speaking && nowMs - this.aboveSinceMs >= this.opts.minSpeechMs) this.speaking = true;
      if (this.speaking) this.lastVoiceMs = nowMs;
    } else {
      this.aboveSinceMs = null;
    }

    if (elapsed >= this.opts.maxMs) return this.speaking ? "stop" : "abort";
    if (this.speaking && nowMs - this.lastVoiceMs >= this.opts.silenceMs) return "stop";
    if (!this.speaking && elapsed >= this.opts.noSpeechMs) return "abort";
    return "continue";
  }
}
