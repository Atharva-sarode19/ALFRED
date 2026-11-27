import { useCallback, useEffect, useRef, useState, type ChangeEvent } from "react";
import { deleteFile, listFiles, listReminders, uploadFile } from "../services/api";
import type { FileInfo, MemoryStatus, Reminder } from "../types";
import "./WorkspacePanel.css";

interface WorkspacePanelProps {
  /** Changes whenever the agent finishes a turn, so the lists reload. */
  refreshKey: number;
  /** Persistent memory status as reported by the backend (null until loaded). */
  memory?: MemoryStatus | null;
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function plural(count: number, noun: string): string {
  return `${count} ${noun}${count === 1 ? "" : "s"}`;
}

function memorySummary(memory: MemoryStatus | null | undefined): string {
  if (!memory) return "Checking…";
  if (!memory.enabled) return "Off — no database configured";
  if (!memory.connected) return "Offline — database unreachable";
  const active = memory.memories?.active;
  return active === undefined ? "Ready" : `Ready · ${plural(active, "saved item")}`;
}

export function WorkspacePanel({ refreshKey, memory }: WorkspacePanelProps) {
  const [open, setOpen] = useState(false);
  const [files, setFiles] = useState<FileInfo[]>([]);
  const [reminders, setReminders] = useState<Reminder[]>([]);
  const [status, setStatus] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirmingId, setConfirmingId] = useState<string | null>(null);
  const [removingId, setRemovingId] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);

  const load = useCallback(async () => {
    try {
      const [loadedFiles, loadedReminders] = await Promise.all([listFiles(), listReminders()]);
      setFiles(loadedFiles);
      setReminders(loadedReminders);
    } catch {
      setStatus("Couldn't reach the server to load your documents and reminders.");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load, refreshKey]);

  const handlePick = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;

    setBusy(true);
    setStatus(null);
    try {
      await uploadFile(file);
      setStatus(`Uploaded ${file.name}. Ask Alfred about it.`);
      await load();
    } catch (err) {
      setStatus(err instanceof Error ? err.message : "Upload failed.");
    } finally {
      setBusy(false);
    }
  };

  // The list only changes after the backend confirms the deletion, then it is re-read from the server.
  const handleRemove = async (file: FileInfo) => {
    setRemovingId(file.id);
    setStatus(null);
    try {
      await deleteFile(file.id);
      setConfirmingId(null);
      setStatus(`Removed ${file.name}.`);
      await load();
    } catch (err) {
      setStatus(err instanceof Error ? `Couldn't remove ${file.name}: ${err.message}` : `Couldn't remove ${file.name}.`);
    } finally {
      setRemovingId(null);
    }
  };

  return (
    <section className="workspace">
      <button
        type="button"
        className="workspace__toggle"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
      >
        <span>Workspace</span>
        <span className="workspace__summary">
          {plural(files.length, "document")}, {plural(reminders.length, "reminder")}
        </span>
      </button>

      {open && (
        <div className="workspace__body">
          <div className="workspace__column">
            <div className="workspace__heading">
              <h2>Documents</h2>
              <button type="button" onClick={() => inputRef.current?.click()} disabled={busy}>
                {busy ? "Uploading" : "Upload"}
              </button>
              <input
                ref={inputRef}
                type="file"
                accept=".pdf,.docx,.txt"
                onChange={handlePick}
                hidden
                aria-label="Upload a PDF, DOCX or TXT document"
              />
            </div>
            {files.length === 0 ? (
              <p className="workspace__empty">Upload a PDF, DOCX or TXT file, then ask Alfred about it.</p>
            ) : (
              <ul className="workspace__list">
                {files.map((file) => (
                  <li key={file.id}>
                    <span className="workspace__name">{file.name}</span>
                    <span className="workspace__meta">{formatSize(file.size_bytes)}</span>
                    {confirmingId === file.id ? (
                      <span className="workspace__remove-confirm" role="group" aria-label={`Remove ${file.name}?`}>
                        <button type="button" onClick={() => void handleRemove(file)} disabled={removingId === file.id}>
                          {removingId === file.id ? "Removing" : "Remove"}
                        </button>
                        <button type="button" onClick={() => setConfirmingId(null)} disabled={removingId === file.id}>
                          Keep
                        </button>
                      </span>
                    ) : (
                      <button
                        type="button"
                        className="workspace__remove"
                        onClick={() => setConfirmingId(file.id)}
                        aria-label={`Remove ${file.name}`}
                        title="Remove document"
                      >
                        <svg viewBox="0 0 16 16" width="10" height="10" aria-hidden="true" focusable="false">
                          <path d="M3 3l10 10M13 3L3 13" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                        </svg>
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="workspace__column">
            <div className="workspace__heading">
              <h2>Reminders</h2>
            </div>
            {reminders.length === 0 ? (
              <p className="workspace__empty">No upcoming reminders. Ask Alfred to set one.</p>
            ) : (
              <ul className="workspace__list">
                {reminders.map((reminder) => (
                  <li key={reminder.id}>
                    <span className="workspace__name">{reminder.title}</span>
                    <span className="workspace__meta">{new Date(reminder.due_utc).toLocaleString()}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <p className="workspace__memory">
            <span>Memory</span>
            <span>{memorySummary(memory)}</span>
          </p>

          {status && <p className="workspace__status">{status}</p>}
        </div>
      )}
    </section>
  );
}
