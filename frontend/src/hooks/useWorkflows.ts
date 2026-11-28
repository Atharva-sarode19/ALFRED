import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { answerWorkflowApproval, cancelWorkflow, getWorkflow, listWorkflows, resumeWorkflow } from "../services/api";
import type { Workflow } from "../types";
import { isActiveWorkflow, pendingTask, visibleWorkflows } from "../utils/workflow";

const POLL_MS = 1500;

/**
 * Workflow progress as the backend reports it. Polls only while a workflow is active (or a chat turn is in
 * flight, since the agent may be starting one); otherwise it reads once per `refreshKey` change.
 */
export function useWorkflows(refreshKey: number, busy: boolean) {
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [dismissed, setDismissed] = useState<ReadonlySet<string>>(new Set());
  const [actionError, setActionError] = useState<string | null>(null);
  // Finished workflows the user has already looked at (Activity opened, or a new interaction began).
  const [acknowledged, setAcknowledged] = useState<ReadonlySet<string>>(new Set());
  const loadedAt = useRef(Date.now());

  const refresh = useCallback(async (signal?: AbortSignal) => {
    try {
      const list = await listWorkflows(signal);
      const shown = visibleWorkflows(list, loadedAt.current, new Set()).slice(0, 3);
      const detailed = await Promise.all(shown.map((w) => getWorkflow(w.id, signal).catch(() => w)));
      setWorkflows(detailed);
    } catch {
      /* backend unreachable or aborted: keep what we have */
    }
  }, []);

  const anyActive = workflows.some((w) => isActiveWorkflow(w.status));
  const polling = anyActive || busy;

  useEffect(() => {
    const controller = new AbortController();
    void refresh(controller.signal);
    if (!polling) return () => controller.abort();
    const id = setInterval(() => void refresh(controller.signal), POLL_MS);
    return () => {
      controller.abort();
      clearInterval(id);
    };
  }, [refresh, refreshKey, polling]);

  const replace = useCallback((updated: Workflow) => {
    setWorkflows((prev) => prev.map((w) => (w.id === updated.id ? updated : w)));
  }, []);

  const run = useCallback(
    async (action: () => Promise<Workflow>) => {
      setActionError(null);
      try {
        replace(await action());
      } catch (err) {
        setActionError(err instanceof Error ? err.message : "That action failed.");
      }
      void refresh();
    },
    [refresh, replace]
  );

  const visible = useMemo(() => visibleWorkflows(workflows, loadedAt.current, dismissed), [workflows, dismissed]);

  // What the main screen previews: everything still active, plus finished ones not yet acknowledged.
  const attention = useMemo(
    () => visible.filter((w) => isActiveWorkflow(w.status) || !acknowledged.has(w.id)),
    [visible, acknowledged]
  );

  const acknowledgeFinished = useCallback(() => {
    setAcknowledged((prev) => {
      const fresh = visible.filter((w) => !isActiveWorkflow(w.status) && !prev.has(w.id));
      return fresh.length === 0 ? prev : new Set([...prev, ...fresh.map((w) => w.id)]);
    });
  }, [visible]);

  return {
    workflows: visible,
    attention,
    acknowledgeFinished,
    needsApproval: visible.some((w) => pendingTask(w) !== undefined),
    actionError,
    dismiss: (id: string) => setDismissed((prev) => new Set(prev).add(id)),
    answerApproval: (w: Workflow, approve: boolean) => {
      const task = pendingTask(w);
      if (task?.pending_approval) void run(() => answerWorkflowApproval(w.id, approve, task.id, task.pending_approval!.call_id));
    },
    cancel: (w: Workflow) => void run(() => cancelWorkflow(w.id)),
    resume: (w: Workflow, retryFailed: boolean) => void run(() => resumeWorkflow(w.id, retryFailed)),
  };
}

export type WorkflowsController = ReturnType<typeof useWorkflows>;
