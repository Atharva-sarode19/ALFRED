import { useEffect, useRef } from "react";
import type { AlfredState } from "../types";
import "./OrbitalCore.css";

interface OrbitalCoreProps {
  state: AlfredState;
  onPress: () => void;
}

const STATE_LABEL: Record<AlfredState, string> = {
  idle: "Press to speak",
  listening: "Listening — press to stop",
  processing: "Reading back what you said",
  thinking: "Thinking",
  executing: "Working",
  speaking: "Speaking",
  error: "Something went wrong",
};

// speed, scale, glow, jitter per state — same tuning as the prototype,
// plus an "error" state the prototype never needed.
const PARAMS: Record<AlfredState, { speed: number; scale: number; glow: number; jitter: number }> = {
  idle: { speed: 0.1, scale: 1.0, glow: 0.35, jitter: 0.0 },
  listening: { speed: 0.16, scale: 0.92, glow: 0.75, jitter: 0.35 },
  processing: { speed: 0.2, scale: 0.96, glow: 0.6, jitter: 0.15 },
  thinking: { speed: 0.55, scale: 1.0, glow: 0.55, jitter: 0.05 },
  executing: { speed: 0.75, scale: 1.05, glow: 0.95, jitter: 0.1 },
  speaking: { speed: 0.3, scale: 1.1, glow: 0.85, jitter: 0.55 },
  error: { speed: 0.05, scale: 0.95, glow: 0.9, jitter: 0.0 },
};

const RINGS = [
  { tiltX: 0.15, tiltZ: 0.0, spin: 1.0, segs: 96 },
  { tiltX: 1.15, tiltZ: 0.3, spin: -0.62, segs: 96 },
  { tiltX: -0.95, tiltZ: 1.0, spin: 0.44, segs: 96 },
  { tiltX: 0.55, tiltZ: -1.4, spin: -0.31, segs: 96 },
];

function makeCorePoints(n = 90) {
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

function rotX(p: [number, number, number], a: number): [number, number, number] {
  const c = Math.cos(a), s = Math.sin(a);
  return [p[0], p[1] * c - p[2] * s, p[1] * s + p[2] * c];
}
function rotZ(p: [number, number, number], a: number): [number, number, number] {
  const c = Math.cos(a), s = Math.sin(a);
  return [p[0] * c - p[1] * s, p[0] * s + p[1] * c, p[2]];
}
function rotY(p: [number, number, number], a: number): [number, number, number] {
  const c = Math.cos(a), s = Math.sin(a);
  return [p[0] * c + p[2] * s, p[1], -p[0] * s + p[2] * c];
}

export function OrbitalCore({ state, onPress }: OrbitalCoreProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const stateRef = useRef(state);
  const blendRef = useRef({ ...PARAMS.idle });
  const corePoints = useRef(makeCorePoints());

  useEffect(() => {
    stateRef.current = state;
  }, [state]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let raf = 0;
    let t = 0;
    let W = 0, H = 0;
    const DPR = Math.min(window.devicePixelRatio || 1, 2);

    function resize() {
      const parent = canvas!.parentElement;
      W = parent ? parent.clientWidth : 320;
      H = parent ? parent.clientHeight : 320;
      canvas!.width = W * DPR;
      canvas!.height = H * DPR;
      canvas!.style.width = `${W}px`;
      canvas!.style.height = `${H}px`;
      ctx!.setTransform(DPR, 0, 0, DPR, 0, 0);
    }
    resize();
    window.addEventListener("resize", resize);

    function project(p: [number, number, number], radius: number, focal: number): [number, number, number] {
      const z = p[2] * radius + focal;
      const f = focal / z;
      return [p[0] * radius * f, p[1] * radius * f, z];
    }

    function draw() {
      ctx!.clearRect(0, 0, W, H);
      const cx = W / 2, cy = H / 2;
      const base = Math.min(W, H) * 0.42;

      const target = PARAMS[stateRef.current];
      const ease = 0.06;
      const b = blendRef.current;
      b.speed += (target.speed - b.speed) * ease;
      b.scale += (target.scale - b.scale) * ease;
      b.glow += (target.glow - b.glow) * ease;
      b.jitter += (target.jitter - b.jitter) * ease;

      const radius = base * b.scale;
      const focal = base * 3.2;

      ctx!.save();
      ctx!.translate(cx, cy);

      RINGS.forEach((ring, ri) => {
        const angle = t * b.speed * ring.spin;
        const pts2d: [number, number, number][] = [];
        for (let i = 0; i <= ring.segs; i++) {
          const a = (i / ring.segs) * Math.PI * 2;
          let p: [number, number, number] = [Math.cos(a), Math.sin(a), 0];
          p = rotX(p, ring.tiltX);
          p = rotZ(p, ring.tiltZ);
          p = rotY(p, angle);
          p = rotX(p, 0.35);
          const wob = b.jitter * 0.02 * Math.sin(t * 3 + i * 0.5 + ri);
          p[2] += wob;
          pts2d.push(project(p, radius, focal));
        }
        ctx!.beginPath();
        pts2d.forEach((p, i) => {
          const depth = p[2] / focal;
          const alpha = Math.max(0.08, Math.min(1, (depth - 0.55) * 2.1)) * (0.35 + b.glow * 0.65);
          if (i === 0) {
            ctx!.moveTo(p[0], p[1]);
          } else {
            ctx!.strokeStyle = `rgba(231,231,234,${alpha.toFixed(3)})`;
            ctx!.lineWidth = 1;
            ctx!.lineTo(p[0], p[1]);
            ctx!.stroke();
            ctx!.beginPath();
            ctx!.moveTo(p[0], p[1]);
          }
        });
      });

      corePoints.current.forEach((pt) => {
        let p: [number, number, number] = [pt[0], pt[1], pt[2]];
        p = rotY(p, t * b.speed * 0.7 + pt[3]);
        p = rotX(p, t * b.speed * 0.4);
        const proj = project(p, radius * 0.34, focal);
        const depth = proj[2] / focal;
        const alpha = Math.max(0.05, Math.min(1, (depth - 0.4) * 1.4)) * (0.4 + b.glow * 0.6);
        const size = 1.1 + depth * 1.1;
        ctx!.beginPath();
        ctx!.fillStyle = `rgba(255,255,255,${alpha.toFixed(3)})`;
        ctx!.arc(proj[0], proj[1], size, 0, Math.PI * 2);
        ctx!.fill();
      });

      const glow = ctx!.createRadialGradient(0, 0, radius * 0.1, 0, 0, radius * 1.5);
      const glowColor = stateRef.current === "error" ? "231,120,120" : "255,255,255";
      glow.addColorStop(0, `rgba(${glowColor},${(0.05 + b.glow * 0.05).toFixed(3)})`);
      glow.addColorStop(1, "rgba(255,255,255,0)");
      ctx!.globalCompositeOperation = "destination-over";
      ctx!.fillStyle = glow;
      ctx!.beginPath();
      ctx!.arc(0, 0, radius * 1.5, 0, Math.PI * 2);
      ctx!.fill();
      ctx!.globalCompositeOperation = "source-over";

      ctx!.restore();
    }

    function tick() {
      t += reduceMotion ? 0.002 : 0.012;
      draw();
      raf = requestAnimationFrame(tick);
    }
    tick();

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
    };
  }, []);

  return (
    <div className="orbital-core">
      <button
        type="button"
        className={`orbital-core__button orbital-core__button--${state}`}
        onClick={onPress}
        aria-pressed={state === "listening"}
        aria-label={STATE_LABEL[state]}
      >
        <canvas ref={canvasRef} className="orbital-core__canvas" aria-hidden="true" />
      </button>
      <p className="orbital-core__label">{STATE_LABEL[state]}</p>
    </div>
  );
}
