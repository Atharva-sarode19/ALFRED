import { useState } from "react";
import type { TraceStep } from "../types";
import "./ActivityTrace.css";

interface ActivityTraceProps {
  trace: TraceStep[];
}

export function ActivityTrace({ trace }: ActivityTraceProps) {
  const [open, setOpen] = useState(false);

  return (
    <section className="activity-trace">
      <button
        type="button"
        className="activity-trace__toggle"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <span>Agent activity</span>
        <span className="activity-trace__count">{trace.length}</span>
      </button>
      {open && (
        <ol className="activity-trace__list">
          {trace.length === 0 && <li className="activity-trace__empty">No activity yet.</li>}
          {trace.map((step, index) => (
            <li key={`${step.stage}-${index}`} className="activity-trace__item">
              <span className="activity-trace__mark">✓</span>
              <span>{step.detail}</span>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
