/**
 * Pointer-drag logic for the orb, kept free of React and the DOM so it can be unit tested.
 *
 * A press only becomes a drag once the pointer has moved DRAG_THRESHOLD_PX; until then it is still a
 * click ("press to speak"). Only a press that STARTS on the orb can drag; once a drag has started it
 * follows the pointer until release, even if the cursor wanders outside the orb (like dragging a 3D
 * object). Conventions match OrbController.rotateBy: moving right turns the front surface right,
 * moving down turns it downward.
 */

export const DRAG_THRESHOLD_PX = 6;
export const DRAG_RADIANS_PER_PX = 0.009;

export interface DragMove {
  dyaw: number;
  dpitch: number;
  /** True on the move that turned the press into a drag. */
  started: boolean;
}

export class OrbDrag {
  private pointerId: number | null = null;
  private originX = 0;
  private originY = 0;
  private lastX = 0;
  private lastY = 0;
  private active = false;

  /** Is a press being tracked (it may still turn out to be a plain click)? */
  get tracking(): boolean {
    return this.pointerId !== null;
  }

  /** Has the press turned into a real drag? */
  get dragging(): boolean {
    return this.active;
  }

  /** Start tracking a press. Presses outside the orb are ignored. Returns whether tracking began. */
  begin(pointerId: number, x: number, y: number, insideOrb: boolean): boolean {
    this.cancel();
    if (!insideOrb) return false;
    this.pointerId = pointerId;
    this.originX = this.lastX = x;
    this.originY = this.lastY = y;
    return true;
  }

  /** Feed a pointer move. Returns the rotation to apply, or null when this move must not rotate. */
  move(pointerId: number, x: number, y: number): DragMove | null {
    if (this.pointerId === null || pointerId !== this.pointerId) return null;
    let started = false;
    if (!this.active) {
      if (Math.hypot(x - this.originX, y - this.originY) < DRAG_THRESHOLD_PX) return null; // still a click
      this.active = true;
      started = true;
    }
    const dx = x - this.lastX;
    const dy = y - this.lastY;
    this.lastX = x;
    this.lastY = y;
    return { dyaw: dx * DRAG_RADIANS_PER_PX, dpitch: dy * DRAG_RADIANS_PER_PX, started };
  }

  /** Release / cancel / lost capture. Returns true if a real drag was in progress. Idempotent. */
  end(pointerId?: number): boolean {
    if (pointerId !== undefined && this.pointerId !== null && pointerId !== this.pointerId) return false;
    return this.cancel();
  }

  private cancel(): boolean {
    const wasDragging = this.active;
    this.pointerId = null;
    this.active = false;
    return wasDragging;
  }
}

/**
 * Screen radius of the orb's visible silhouette. The sphere has radius `radius` and is drawn with a
 * perspective camera at distance `focal`, so its nearest points appear enlarged by focal / (focal - radius).
 */
export function silhouetteRadius(radius: number, focal: number): number {
  return radius >= focal ? Number.POSITIVE_INFINITY : (radius * focal) / (focal - radius);
}

/** Is (x, y) within `radius` (+ `pad`) of (cx, cy)? All values in the same units. */
export function insideOrb(x: number, y: number, cx: number, cy: number, radius: number, pad = 2): boolean {
  return Math.hypot(x - cx, y - cy) <= radius + pad;
}

/**
 * Eases the orb's automatic spin factor (1 = full speed, 0 = stopped) toward 0 while `hold` is true
 * (the user is dragging, or paused the spin) and back toward 1 when released. The renderer multiplies its
 * spin speed by this factor and keeps integrating the same angles, so switching never jumps or resets.
 */
export function easeAutoSpin(current: number, hold: boolean, dtSeconds: number): number {
  return current + ((hold ? 0 : 1) - current) * (1 - Math.exp(-4 * Math.max(0, dtSeconds)));
}
