import { useEffect, useRef, useState, type FormEvent } from "react";
import "./TextComposer.css";

interface TextComposerProps {
  open: boolean;
  /** Goes through the same agent flow as a spoken request. */
  onSend: (message: string) => Promise<void> | void;
  onClose: () => void;
}

export function TextComposer({ open, onSend, onClose }: TextComposerProps) {
  const [value, setValue] = useState("");
  const inputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const message = value.trim();
    if (!message) return;
    setValue("");
    onClose();
    void onSend(message);
  };

  return (
    <form
      id="text-composer"
      className={`text-composer ${open ? "text-composer--open" : ""}`}
      onSubmit={submit}
      aria-hidden={!open}
    >
      <input
        ref={inputRef}
        type="text"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder="Type to ALFRED…"
        aria-label="Type a message to ALFRED"
        tabIndex={open ? 0 : -1}
        autoComplete="off"
      />
      <button type="submit" tabIndex={open ? 0 : -1} disabled={!value.trim()}>
        Send
      </button>
    </form>
  );
}
