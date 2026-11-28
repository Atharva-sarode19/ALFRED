import "./ControlBar.css";

export type PanelId = "history" | "text" | "activity";

interface ControlBarProps {
  open: PanelId | null;
  onToggle: (panel: PanelId) => void;
  /** Dot on Activity: something there needs the user's approval. */
  attention: boolean;
  /** Subtle dot on Activity: a workflow is working, or failed unseen. Approval (`attention`) takes precedence. */
  activity?: "working" | "failed" | null;
}

const ITEMS: { id: PanelId; label: string; controls: string }[] = [
  { id: "history", label: "History", controls: "history-sheet" },
  { id: "text", label: "Type", controls: "text-composer" },
  { id: "activity", label: "Activity", controls: "activity-panel" },
];

export function ControlBar({ open, onToggle, attention, activity = null }: ControlBarProps) {
  return (
    <nav className="control-bar" aria-label="ALFRED controls">
      {ITEMS.map((item) => (
        <button
          key={item.id}
          type="button"
          className={`control-bar__btn ${open === item.id ? "control-bar__btn--active" : ""}`}
          onClick={() => onToggle(item.id)}
          aria-expanded={open === item.id}
          aria-controls={item.controls}
        >
          {item.label}
          {item.id === "activity" && attention && <span className="control-bar__dot" aria-label="Approval needed" />}
          {item.id === "activity" && !attention && activity && (
            <span
              className={`control-bar__dot control-bar__dot--${activity}`}
              aria-label={activity === "working" ? "Workflow running" : "Workflow failed"}
            />
          )}
        </button>
      ))}
    </nav>
  );
}
