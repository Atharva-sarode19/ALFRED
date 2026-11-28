import type { Workflow } from "../types";
import { WORKFLOW_HEADLINE, TASK_LABEL, currentTaskLine, progressPercent, shortTitle, taskMark } from "../utils/workflow";
import "./WorkflowProgress.css";

const GLYPH_STATUSES = new Set(["completed", "failed", "blocked", "cancelled"]);

/** Read-only preview of the workflow on the main screen. Approvals, cancel, retry and results stay in the Activity panel. */
export function WorkflowProgress({ workflow }: { workflow: Workflow }) {
  const task = currentTaskLine(workflow);
  const { completed_tasks: done, total_tasks: total } = workflow;

  return (
    <section className={`wfp wfp--${workflow.status}`} aria-label="Workflow progress" aria-live="polite" title={workflow.title}>
      <p className="wfp__label">{WORKFLOW_HEADLINE[workflow.status]}</p>
      {task && <p className="wfp__task">{task}</p>}

      <div className="wfp__progress">
        <div className="wfp__bar" role="progressbar" aria-valuemin={0} aria-valuemax={total} aria-valuenow={done} aria-label="Tasks completed">
          <span style={{ width: `${progressPercent(workflow)}%` }} />
        </div>
        <span className="wfp__count">
          {done}/{total}
        </span>
      </div>

      <ol className="wfp__timeline">
        {workflow.tasks.map((t) => (
          <li key={t.id} className={`wfp__step wfp__step--${t.status}`} title={`${t.description} · ${TASK_LABEL[t.status]}`}>
            <span className="wfp__icon" aria-hidden="true">
              {GLYPH_STATUSES.has(t.status) ? taskMark(t.status) : ""}
            </span>
            <span className="wfp__step-title">{shortTitle(t.description)}</span>
            <span className="wfp__sr">{TASK_LABEL[t.status]}</span>
          </li>
        ))}
      </ol>
    </section>
  );
}
