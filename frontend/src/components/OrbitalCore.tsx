import { useEffect, useRef, type PointerEvent as ReactPointerEvent } from "react";
import type { OrbController } from "../orb/orbController";
import { OrbDrag, easeAutoSpin, insideOrb, silhouetteRadius } from "../orb/orbDrag";
import type { AlfredState } from "../types";
import "./OrbitalCore.css";

interface OrbitalCoreProps {
  state: AlfredState;
  onPress: () => void;
  /** Rotation, size, pause and audio level, written by mouse/keyboard/audio. */
  controller: OrbController;
}

const STATE_LABEL: Record<AlfredState, string> = {
  idle: "Press to speak",
  listening: "Listening — press to stop",
  processing: "Reading back what you said",
  thinking: "Thinking — press to cancel",
  executing: "Working — press to cancel",
  speaking: "Speaking — press to stop",
  error: "Something went wrong",
};

// Per-state look. pulse = breathing amplitude, rate = pulse rad/s, spread = how much the rings
// diverge in speed (executing), err = error tint 0..1. Every value is eased, so transitions never snap.
interface OrbParams {
  speed: number;
  scale: number;
  glow: number;
  jitter: number;
  pulse: number;
  rate: number;
  spread: number;
  err: number;
}
const PARAMS: Record<AlfredState, OrbParams> = {
  idle: { speed: 0.1, scale: 1.0, glow: 0.35, jitter: 0.0, pulse: 0, rate: 1, spread: 0, err: 0 },
  listening: { speed: 0.16, scale: 1.04, glow: 0.7, jitter: 0.3, pulse: 0.018, rate: 2.4, spread: 0, err: 0 },
  processing: { speed: 0.3, scale: 0.99, glow: 0.55, jitter: 0.15, pulse: 0.01, rate: 3, spread: 0.2, err: 0 },
  thinking: { speed: 0.45, scale: 1.0, glow: 0.55, jitter: 0.18, pulse: 0.012, rate: 3.4, spread: 0.45, err: 0 },
  executing: { speed: 0.7, scale: 1.02, glow: 0.8, jitter: 0.1, pulse: 0.008, rate: 5, spread: 1.0, err: 0 },
  speaking: { speed: 0.26, scale: 1.04, glow: 0.75, jitter: 0.25, pulse: 0.028, rate: 3.2, spread: 0, err: 0 },
  error: { speed: 0.05, scale: 0.97, glow: 0.6, jitter: 0.0, pulse: 0, rate: 1, spread: 0, err: 1 },
};

const RINGS = [
  { tiltX: 0.15, tiltZ: 0.0, spin: 1.0, segs: 96 },
  { tiltX: 1.15, tiltZ: 0.3, spin: -0.62, segs: 96 },
  { tiltX: -0.95, tiltZ: 1.0, spin: 0.44, segs: 96 },
  { tiltX: 0.55, tiltZ: -1.4, spin: -0.31, segs: 96 },
];

/** Angular rate (rad/s) at speed 1 -- the original animation's pace. */
const TIME_RATE = 0.72;
const CORE_POINTS = 220;
const IDLE_FRAME_MS = 33; // ~30 fps in standby, full rate when something is happening

type V3 = [number, number, number];

function makeCorePoints(n: number) {
  const pts: [number, number, number, number][] = [];
  for (let i = 0; i < n; i++) {
    const u = Math.random() * 2 - 1;
    const t = Math.random() * Math.PI * 2;
    const r = Math.cbrt(Math.random());
    const s = Math.sqrt(1 - u * u);
    pts.push([r * s * Math.cos(t), r * s * Math.sin(t), r * u, Math.random() * Math.PI * 2]);
  }
  return pts;
}

function rotX(p: V3, a: number): V3 {
  const c = Math.cos(a), s = Math.sin(a);
  return [p[0], p[1] * c - p[2] * s, p[1] * s + p[2] * c];
}
function rotZ(p: V3, a: number): V3 {
  const c = Math.cos(a), s = Math.sin(a);
  return [p[0] * c - p[1] * s, p[0] * s + p[1] * c, p[2]];
}
function rotY(p: V3, a: number): V3 {
  const c = Math.cos(a), s = Math.sin(a);
  return [p[0] * c + p[2] * s, p[1], -p[0] * s + p[2] * c];
}

export function OrbitalCore({ state, onPress, controller }: OrbitalCoreProps) {
  const buttonRef = useRef<HTMLButtonElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const stateRef = useRef(state);
  const blendRef = useRef({ ...PARAMS.idle });
  const corePoints = useRef(makeCorePoints(CORE_POINTS));
  const draggedRef = useRef(false);
  const dragRef = useRef(new OrbDrag());
  /** Screen radius (CSS px) of the orb as last drawn: only a press inside it can start a drag. */
  const silhouetteRef = useRef(0);

  useEffect(() => {
    stateRef.current = state;
  }, [state]);

  // ---- render loop -----------------------------------------------------
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const motion = reduceMotion ? 0.17 : 1;
    const DPR = Math.min(window.devicePixelRatio || 1, 2);
    let W = 0;
    let H = 0;
    let raf = 0;
    let last = performance.now();
    let run = 1; // 1 = auto-rotating, eases to 0 when paused
    let shimmerT = 0;
    let coreT = 0;
    let pulseT = 0;
    const ringAngles = RINGS.map(() => 0);

    function resize() {
      const parent = canvas!.parentElement;
      W = parent ? parent.clientWidth : 320;
      H = parent ? parent.clientHeight : 320;
      canvas!.width = Math.round(W * DPR);
      canvas!.height = Math.round(H * DPR);
      canvas!.style.width = `${W}px`;
      canvas!.style.height = `${H}px`;
      ctx!.setTransform(DPR, 0, 0, DPR, 0, 0);
    }
    resize();
    const observer = new ResizeObserver(resize);
    if (canvas.parentElement) observer.observe(canvas.parentElement);

    function project(p: V3, radius: number, focal: number): V3 {
      const z = p[2] * radius + focal;
      const f = focal / z;
      return [p[0] * radius * f, p[1] * radius * f, z];
    }

    function draw(dt: number) {
      const st = stateRef.current;
      const snap = controller.step(dt);

      // ease the per-state look toward its target (frame-rate independent)
      const ease = 1 - Math.exp(-dt * 3.6);
      const target = PARAMS[st];
      const b = blendRef.current;
      b.speed += (target.speed - b.speed) * ease;
      b.scale += (target.scale - b.scale) * ease;
      b.glow += (target.glow - b.glow) * ease;
      b.jitter += (target.jitter - b.jitter) * ease;
      b.pulse += (target.pulse - b.pulse) * ease;
      b.rate += (target.rate - b.rate) * ease;
      b.spread += (target.spread - b.spread) * ease;
      b.err += (target.err - b.err) * ease;
      // the automatic spin eases out while the user holds the orb and eases back in on release
      run = easeAutoSpin(run, snap.paused || snap.dragging, dt);

      shimmerT += dt;
      pulseT += dt * b.rate; // phase accumulates, so a rate change never jumps the pulse
      const level = snap.level;
      const speed = b.speed * run * motion * TIME_RATE;
      for (let i = 0; i < RINGS.length; i++) ringAngles[i] += dt * speed * RINGS[i].spin * (1 + b.spread * (0.35 - 0.3 * i));
      coreT += dt * speed;

      const base = Math.min(W, H) * 0.27;
      const focal = base * 4.2;
      const breath = Math.sin(pulseT) * b.pulse * (reduceMotion ? 0.3 : 1);
      const pulse = 1 + breath * 5; // inner particle cluster breathes more than the rings
      const radius = base * b.scale * snap.scale * (1 + 0.12 * level + breath);
      // error tint: eased from the neutral ink toward a desaturated red
      const tr = Math.round(231 + b.err * 4), tg = Math.round(231 - b.err * 101), tb = Math.round(234 - b.err * 104);
      const glowAmt = Math.min(1, b.glow + 0.45 * level);
      const jitter = b.jitter + 0.6 * level;
      const sizeScale = Math.min(2.4, Math.max(1, base / 92)) * 0.75;
      silhouetteRef.current = silhouetteRadius(radius, focal);

      // user view rotation: drag yaw (front surface follows the cursor) and pitch
      const view = (p: V3): V3 => rotX(rotY(p, -snap.yaw), snap.pitch);
      // 0 = farthest, 1 = nearest point of the sphere
      const nearness = (z: number) => Math.min(1, Math.max(0, (focal + radius - z) / (2 * radius)));

      ctx!.clearRect(0, 0, W, H);
      ctx!.save();
      ctx!.translate(W / 2, H / 2);
      ctx!.lineWidth = Math.max(1, base / 130);

      RINGS.forEach((ring, ri) => {
        const pts: V3[] = [];
        const nears: number[] = [];
        for (let i = 0; i <= ring.segs; i++) {
          const a = (i / ring.segs) * Math.PI * 2;
          let p: V3 = [Math.cos(a), Math.sin(a), 0];
          p = rotX(p, ring.tiltX);
          p = rotZ(p, ring.tiltZ);
          p = rotY(p, ringAngles[ri]);
          p = rotX(p, 0.35);
          p[2] += jitter * 0.02 * Math.sin(shimmerT * 3 + i * 0.5 + ri);
          p = view(p);
          const proj = project(p, radius, focal);
          pts.push(proj);
          nears.push(nearness(proj[2]));
        }

        for (let i = 1; i < pts.length; i++) {
          let alpha = Math.max(0.08, nears[i] ** 1.5) * (0.35 + glowAmt * 0.65);
          if (st === "executing") {
            // a bright pulse travelling around each ring: tool activity
            const phase = (i / ring.segs - (shimmerT * 0.6 + ri * 0.25)) % 1;
            alpha += 0.55 * Math.max(0, Math.cos(phase * Math.PI * 2)) ** 8;
          }
          ctx!.strokeStyle = `rgba(${tr},${tg},${tb},${Math.min(1, alpha).toFixed(3)})`;
          ctx!.beginPath();
          ctx!.moveTo(pts[i - 1][0], pts[i - 1][1]);
          ctx!.lineTo(pts[i][0], pts[i][1]);
          ctx!.stroke();
        }
      });

      corePoints.current.forEach((pt) => {
        let p: V3 = [pt[0], pt[1], pt[2]];
        const shimmer = 1 + jitter * 0.18 * Math.sin(shimmerT * 2.3 + pt[3] * 3);
        p = [p[0] * shimmer, p[1] * shimmer, p[2] * shimmer];
        p = rotY(p, coreT * 0.7 + pt[3]);
        p = rotX(p, coreT * 0.4);
        p = view(p);
        const proj = project(p, radius * 0.34 * pulse, focal);
        const near = nearness(proj[2]);
        const alpha = Math.max(0.05, near) * (0.4 + glowAmt * 0.6);
        ctx!.beginPath();
        ctx!.fillStyle = `rgba(${255 - Math.round(b.err * 24)},${255 - Math.round(b.err * 125)},${255 - Math.round(b.err * 125)},${Math.min(1, alpha).toFixed(3)})`;
        ctx!.arc(proj[0], proj[1], (1.1 + near * 1.4) * sizeScale, 0, Math.PI * 2);
        ctx!.fill();
      });

      const glow = ctx!.createRadialGradient(0, 0, radius * 0.1, 0, 0, radius * 1.5);
      const glowColor = `${tr},${tg},${tb}`;
      glow.addColorStop(0, `rgba(${glowColor},${(0.05 + glowAmt * 0.06).toFixed(3)})`);
      glow.addColorStop(1, "rgba(255,255,255,0)");
      ctx!.globalCompositeOperation = "destination-over";
      ctx!.fillStyle = glow;
      ctx!.beginPath();
      ctx!.arc(0, 0, radius * 1.5, 0, Math.PI * 2);
      ctx!.fill();
      ctx!.globalCompositeOperation = "source-over";
      ctx!.restore();
    }

    function frame(now: number) {
      raf = requestAnimationFrame(frame);
      const idle = (stateRef.current === "idle" || stateRef.current === "error") && !controller.dragging; // full frame rate while dragging
      if (now - last < (idle ? IDLE_FRAME_MS : 0)) return;
      const dt = Math.min(0.1, (now - last) / 1000);
      last = now;
      draw(dt);
    }

    const onVisibility = () => {
      cancelAnimationFrame(raf);
      if (!document.hidden) {
        last = performance.now();
        raf = requestAnimationFrame(frame);
      }
    };
    document.addEventListener("visibilitychange", onVisibility);
    if (!document.hidden) raf = requestAnimationFrame(frame);

    return () => {
      cancelAnimationFrame(raf);
      observer.disconnect();
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [controller]);

  // ---- mouse / touch: drag the orb to rotate it, wheel to resize --------------
  useEffect(() => {
    const button = buttonRef.current;
    if (!button) return;
    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      controller.zoomBy(Math.exp(-event.deltaY * 0.0012));
    };
    button.addEventListener("wheel", onWheel, { passive: false });
    return () => button.removeEventListener("wheel", onWheel);
  }, [controller]);

  // Never leave the orb stuck in "dragging" if the component goes away mid-drag.
  useEffect(
    () => () => {
      dragRef.current.end();
      controller.setDragging(false);
    },
    [controller]
  );

  const pointerOnOrb = (event: ReactPointerEvent<HTMLButtonElement>): boolean => {
    const canvas = canvasRef.current;
    if (!canvas) return false;
    const rect = canvas.getBoundingClientRect();
    return insideOrb(event.clientX, event.clientY, rect.left + rect.width / 2, rect.top + rect.height / 2, silhouetteRef.current);
  };
  /** Cursor feedback: open hand over the orb, closed hand while dragging, the normal pointer elsewhere. */
  const setCursor = (button: HTMLButtonElement, mode: "grab" | "grabbing" | null) => {
    if (mode) button.dataset.cursor = mode;
    else delete button.dataset.cursor;
  };

  const onPointerDown = (event: ReactPointerEvent<HTMLButtonElement>) => {
    draggedRef.current = false;
    if (event.pointerType === "mouse" && event.button !== 0) return; // left button only
    if (!event.isPrimary) return; // ignore a second finger
    // Only a press that starts ON the orb can rotate it; the rest of the button still works as "press to speak".
    if (dragRef.current.begin(event.pointerId, event.clientX, event.clientY, pointerOnOrb(event))) {
      event.currentTarget.setPointerCapture(event.pointerId);
    }
  };
  const onPointerMove = (event: ReactPointerEvent<HTMLButtonElement>) => {
    const drag = dragRef.current;
    if (!drag.tracking) {
      if (event.pointerType === "mouse") setCursor(event.currentTarget, pointerOnOrb(event) ? "grab" : null);
      return;
    }
    const move = drag.move(event.pointerId, event.clientX, event.clientY);
    if (!move) return; // still a click, or another pointer
    if (move.started) {
      draggedRef.current = true; // a drag must not count as "press to speak"
      controller.setDragging(true);
      setCursor(event.currentTarget, "grabbing");
    }
    controller.rotateBy(move.dyaw, move.dpitch);
  };
  const finishDrag = (event: ReactPointerEvent<HTMLButtonElement>) => {
    if (dragRef.current.end(event.pointerId)) controller.setDragging(false);
    setCursor(event.currentTarget, event.pointerType === "mouse" && pointerOnOrb(event) ? "grab" : null);
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
  };
  const onPointerLeave = (event: ReactPointerEvent<HTMLButtonElement>) => {
    if (!dragRef.current.tracking) setCursor(event.currentTarget, null);
  };
  const onClick = () => {
    if (draggedRef.current) {
      draggedRef.current = false;
      return;
    }
    onPress();
  };

  return (
    <div className="orbital-core">
      <button
        ref={buttonRef}
        type="button"
        className={`orbital-core__button orbital-core__button--${state}`}
        onClick={onClick}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={finishDrag}
        onPointerCancel={finishDrag}
        onLostPointerCapture={finishDrag}
        onPointerLeave={onPointerLeave}
        onDragStart={(event) => event.preventDefault()}
        aria-pressed={state === "listening"}
        aria-label={STATE_LABEL[state]}
        title="Click to talk. Drag to rotate, scroll to resize. Keys: arrows, + / -, P pause, 0 reset, Esc cancel."
      >
        <canvas ref={canvasRef} className="orbital-core__canvas" aria-hidden="true" />
      </button>
      <p className="orbital-core__label" aria-live="polite">
        {STATE_LABEL[state]}
      </p>
    </div>
  );
}
