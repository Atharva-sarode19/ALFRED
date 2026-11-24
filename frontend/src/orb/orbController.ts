/**
 * Shared, framework-free state for the orb: how it is rotated, scaled, paused
 * and how loud ALFRED (or the microphone) currently is.
 *
 * Writers (mouse drag, wheel, keyboard, audio meters) call the setters; the
 * renderer calls `step()` once per frame and draws the returned snapshot.
 * Targets are set instantly and the visible values ease toward them, so no
 * input source has to worry about smoothing or jitter.
 *
 * Conventions: positive yaw turns the orb's front surface to the right,
 * positive pitch turns it downward (i.e. "drag the sphere" semantics).
 */

export interface OrbSnapshot {
  yaw: number;
  pitch: number;
  scale: number;
  level: number;
  paused: boolean;
  /** True while the user is dragging the orb; the renderer eases its automatic spin down meanwhile. */
  dragging: boolean;
}

export const SCALE_MIN = 0.55;
export const SCALE_MAX = 1.35;
export const PITCH_LIMIT = 1.2;

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

export class OrbController {
  private yawTarget = 0;
  private pitchTarget = 0;
  private scaleTarget = 1;
  private levelTarget = 0;
  private yaw = 0;
  private pitch = 0;
  private scale = 1;
  private level = 0;
  private pausedFlag = false;
  private draggingFlag = false;

  get paused(): boolean {
    return this.pausedFlag;
  }

  get dragging(): boolean {
    return this.draggingFlag;
  }

  /** Where the scale is heading. */
  get targetScale(): number {
    return this.scaleTarget;
  }

  rotateBy(dyaw: number, dpitch: number): void {
    this.yawTarget += dyaw;
    this.pitchTarget = clamp(this.pitchTarget + dpitch, -PITCH_LIMIT, PITCH_LIMIT);
  }

  setScale(scale: number): void {
    this.scaleTarget = clamp(scale, SCALE_MIN, SCALE_MAX);
  }

  zoomBy(factor: number): void {
    this.setScale(this.scaleTarget * factor);
  }

  /** Loudness 0..1 of whatever is currently producing sound (mic while listening, TTS while speaking). */
  setLevel(level: number): void {
    this.levelTarget = clamp(Number.isFinite(level) ? level : 0, 0, 1);
  }

  /** The user is (or is no longer) dragging the orb by hand. Manual rotation takes over from the auto-spin. */
  setDragging(dragging: boolean): void {
    this.draggingFlag = dragging;
  }

  togglePaused(): boolean {
    this.pausedFlag = !this.pausedFlag;
    return this.pausedFlag;
  }

  setPaused(paused: boolean): void {
    this.pausedFlag = paused;
  }

  reset(): void {
    this.yawTarget = 0;
    this.pitchTarget = 0;
    this.scaleTarget = 1;
    this.pausedFlag = false;
  }

  /** Advance the easing by `dtSeconds` and return what to draw. */
  step(dtSeconds: number): OrbSnapshot {
    const dt = clamp(dtSeconds, 0, 0.1);
    const ease = (rate: number) => 1 - Math.exp(-rate * dt);

    this.yaw += (this.yawTarget - this.yaw) * ease(9);
    this.pitch += (this.pitchTarget - this.pitch) * ease(9);
    this.scale += (this.scaleTarget - this.scale) * ease(7);

    // Loudness rises quickly and falls slowly, which reads as natural motion.
    const rate = this.levelTarget > this.level ? 28 : 6;
    this.level += (this.levelTarget - this.level) * ease(rate);

    // Keep the angle bounded so long sessions never lose float precision.
    const turn = Math.PI * 2;
    if (Math.abs(this.yawTarget) > turn * 4 && Math.abs(this.yaw) > turn * 4) {
      const whole = Math.trunc(this.yaw / turn) * turn;
      this.yaw -= whole;
      this.yawTarget -= whole;
    }

    return {
      yaw: this.yaw,
      pitch: this.pitch,
      scale: this.scale,
      level: this.level,
      paused: this.pausedFlag,
      dragging: this.draggingFlag,
    };
  }
}
