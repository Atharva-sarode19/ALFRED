import { useCallback, useEffect, useRef, useState, type ChangeEvent } from "react";
import { listFiles, listReminders, uploadFile } from "../services/api";
import type { FileInfo, Reminder } from "../types";
import "./WorkspacePanel.css";

interface WorkspacePanelProps {
  /** Changes whenever the agent finishes a turn, so the lists reload. */
  refreshKey: number;
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function plural(count: number, noun: string): string {
  return `${count} ${noun}${count === 1 ? "" : "s"}`;
}

export function WorkspacePanel({ refreshKey }: WorkspacePanelProps) {
  const [open, setOpen] = useState(false);
  const [files, setFiles] = useState<FileInfo[]>([]);
  const [reminders, setReminders] = useState<Reminder[]>([]);
  const [status, setStatus] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
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

          {status && <p className="workspace__status">{status}</p>}
        </div>
      )}
    </section>
  );
}
