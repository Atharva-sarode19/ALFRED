import { useEffect, useState } from "react";
import { getMemoryStatus } from "../services/api";
import type { MemoryStatus } from "../types";

const RECALL_VISIBLE_MS = 6000;

export type MemoryIndicator = "unknown" | "off" | "offline" | "ready" | "retrieved";

/**
 * Memory state as the backend actually reports it: GET /api/memory/status (re-read after each
 * turn) plus the `memory_retrieved` trace note, surfaced via `recallKey`. "Context retrieved"
 * fades back to "ready" on its own. There is no live "recalling" signal: the API answers once,
 * after the turn, so that state is deliberately not shown.
 */
export function useMemoryStatus(refreshKey: number, recallKey: number) {
  const [status, setStatus] = useState<MemoryStatus | null>(null);
  const [failed, setFailed] = useState(false);
  const [recalled, setRecalled] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    getMemoryStatus(controller.signal)
      .then((s) => {
        setStatus(s);
        setFailed(false);
      })
      .catch(() => {
        if (!controller.signal.aborted) setFailed(true);
      });
    return () => controller.abort();
  }, [refreshKey]);

  useEffect(() => {
    if (recallKey === 0) return;
    setRecalled(true);
    const id = setTimeout(() => setRecalled(false), RECALL_VISIBLE_MS);
    return () => clearTimeout(id);
  }, [recallKey]);

  let indicator: MemoryIndicator = "unknown";
  if (failed) indicator = "offline";
  else if (status) indicator = !status.enabled ? "off" : !status.connected ? "offline" : recalled ? "retrieved" : "ready";
  return { status, indicator };
}
