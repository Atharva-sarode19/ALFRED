import { useEffect, useRef } from "react";
import type { ActivityEvent, ActivityStatus, PendingConfirmation } from "../types";
import { formatDuration } from "../utils/activity";
import "./ActivityPanel.css";

interface ActivityPanelProps {
  open: boolean;
  events: ActivityEvent[];
  /** True while a request is in flight (the backend does not stream per-tool progress). */
  busy: boolean;
  pending: PendingConfirmation | null;
  onApprove: () => void;
  onReject: () => void;
  onClose: () => void;
}

const STATUS_LABEL: Record<ActivityStatus, string> = {
  pending: "Pending",
  running: "Running",
  completed: "Completed",
  failed: "Failed",
  waiting: "Waiting for approval",
};

const APPROVAL_LABEL = { required: "Approval required", approved: "Approved", declined: "Declined" } as const;

function Row({ event, pending, onApprove, onReject }: { event: ActivityEvent; pending: PendingConfirmation | null } & Pick<ActivityPanelProps, "onApprove" | "onReject">) {
  const awaiting = event.status === "waiting" && pending !== null && pending.tool_name === event.name;
  return (
    <li className="activity__item">
      <span className={`activity__mark activity__mark--${event.status}`} aria-hidden="true" />
      <div className="activity__body">
        <p className="activity__line">
          <span className="activity__name">{event.name}</span>
          <span className="activity__status">
            {STATUS_LABEL[event.status]}
            {event.durationMs !== undefined && <span className="activity__duration"> · {formatDuration(event.durationMs)}</span>}
          </span>
        </p>
        {event.approval && <p className="activity__detail">{APPROVAL_LABEL[event.approval]}</p>}
        {event.detail && <p className="activity__detail">{event.detail}</p>}
        {awaiting && (
          <div className="activity__actions">
            <button type="button" onClick={onApprove}>
              Approve
            </button>
            <button type="button" onClick={onReject}>
              Reject
            </button>
          </div>
        )}
      </div>
    </li>
  );
}

export function ActivityPanel({ open, events, busy, pending, onApprove, onReject, onClose }: ActivityPanelProps) {
  const listRef = useRef<HTMLOListElement | null>(null);

  useEffect(() => {
    const list = listRef.current;
    if (open && list) list.scrollTop = list.scrollHeight;
  }, [open, events.length, busy]);

  return (
    <aside id="activity-panel" className={`activity ${open ? "activity--open" : ""}`} aria-hidden={!open} aria-label="Agent activity">
      <header className="activity__header">
        <h2>Agent activity</h2>
        <button type="button" onClick={onClose} aria-label="Close activity" tabIndex={open ? 0 : -1}>
          <svg viewBox="0 0 16 16" width="12" height="12" aria-hidden="true" focusable="false">
            <path d="M3 3l10 10M13 3L3 13" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
        </button>
      </header>
      <ol className="activity__list" ref={listRef}>
        {events.length === 0 && !busy && <li className="activity__empty">No activity yet.</li>}
        {events.map((event) => (
          <Row key={event.id} event={event} pending={pending} onApprove={onApprove} onReject={onReject} />
        ))}
        {busy && (
          <li className="activity__item">
            <span className="activity__mark activity__mark--running" aria-hidden="true" />
            <div className="activity__body">
              <p className="activity__line">
                <span className="activity__name">Request</span>
                <span className="activity__status">{STATUS_LABEL.running}</span>
              </p>
            </div>
          </li>
        )}
      </ol>
    </aside>
  );
}
