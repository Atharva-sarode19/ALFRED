import type { Workflow } from "../types";
import {
  STATUS_LABEL,
  TASK_LABEL,
  eventTone,
  isActiveWorkflow,
  pendingTask,
  progressLabel,
  resumeOptions,
  taskMark,
} from "../utils/workflow";
import "./WorkflowCard.css";

interface WorkflowCardProps {
  workflow: Workflow;
  onApprove: () => void;
  onReject: () => void;
  onCancel: () => void;
  onResume: (retryFailed: boolean) => void;
  onDismiss: () => void;
}

const EVENT_MARK = { ok: "✓", fail: "✕", wait: "◉", info: "·" } as const;

export function WorkflowCard({ workflow, onApprove, onReject, onCancel, onResume, onDismiss }: WorkflowCardProps) {
  const waiting = pendingTask(workflow);
  const options = resumeOptions(workflow);
  const active = isActiveWorkflow(workflow.status);
  const events = workflow.events ?? [];

  return (
    <section className="wf" aria-label={`Workflow: ${workflow.title}`}>
      <header className="wf__head">
        <p className="wf__label">Task</p>
        {!active && (
          <button type="button" className="wf__dismiss" onClick={onDismiss} aria-label="Dismiss workflow">
            Dismiss
          </button>
        )}
      </header>
      <p className="wf__title">{workflow.title || workflow.request}</p>

      <dl className="wf__meta">
        <div>
          <dt>Status</dt>
          <dd className={`wf__status wf__status--${workflow.status}`}>{STATUS_LABEL[workflow.status]}</dd>
        </div>
        <div>
          <dt>Progress</dt>
          <dd>{progressLabel(workflow)}</dd>
        </div>
      </dl>

      <ul className="wf__tasks">
        {workflow.tasks.map((task) => (
          <li key={task.id} className={`wf__task wf__task--${task.status}`}>
            <span className="wf__mark" aria-hidden="true">
              {taskMark(task.status)}
            </span>
            <div>
              <p className="wf__task-line">
                {task.description}
                <span className="wf__task-status"> · {TASK_LABEL[task.status]}</span>
              </p>
              {task.error && task.status !== "completed" && <p className="wf__detail">{task.error}</p>}
            </div>
          </li>
        ))}
      </ul>

      {waiting?.pending_approval && (
        <div className="wf__approval" role="group" aria-label="Approval needed">
          <p>{waiting.pending_approval.description}. Shall I go ahead, Sir?</p>
          <p className="wf__detail">
            {waiting.pending_approval.tool_name} {JSON.stringify(waiting.pending_approval.arguments)}
          </p>
          <div className="wf__actions">
            <button type="button" onClick={onApprove}>
              Approve
            </button>
            <button type="button" onClick={onReject}>
              Reject
            </button>
          </div>
        </div>
      )}

      {!active && workflow.summary && <p className="wf__summary">{workflow.summary}</p>}
      {workflow.status === "failed" && workflow.failure && <p className="wf__detail">{workflow.failure}</p>}

      {(active || options.continue || options.retryFailed) && (
        <div className="wf__actions">
          {active && (
            <button type="button" onClick={onCancel}>
              Cancel workflow
            </button>
          )}
          {options.continue && (
            <button type="button" onClick={() => onResume(false)}>
              Continue
            </button>
          )}
          {options.retryFailed && (
            <button type="button" onClick={() => onResume(true)}>
              Retry failed
            </button>
          )}
        </div>
      )}

      {workflow.result && (
        <details className="wf__fold">
          <summary>Result</summary>
          <p className="wf__result">{workflow.result}</p>
        </details>
      )}

      {events.length > 0 && (
        <details className="wf__fold">
          <summary>Execution trace ({events.length})</summary>
          <ol className="wf__events">
            {events.map((event) => (
              <li key={event.seq} className={`wf__event wf__event--${eventTone(event.kind)}`}>
                <span aria-hidden="true">{EVENT_MARK[eventTone(event.kind)]}</span> {event.message}
              </li>
            ))}
          </ol>
        </details>
      )}
    </section>
  );
}
