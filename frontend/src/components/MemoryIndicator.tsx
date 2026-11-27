import type { MemoryIndicator as Indicator } from "../hooks/useMemoryStatus";
import "./MemoryIndicator.css";

const LABEL: Partial<Record<Indicator, string>> = {
  ready: "memory ready",
  retrieved: "context retrieved",
  off: "memory off",
  offline: "memory offline",
};

export function MemoryIndicator({ indicator }: { indicator: Indicator }) {
  const label = LABEL[indicator];
  if (!label) return null;
  return (
    <p className={`memory-indicator memory-indicator--${indicator}`} role="status" aria-live="polite" title={label}>
      <span className="memory-indicator__dot" aria-hidden="true" />
      {label}
    </p>
  );
}
