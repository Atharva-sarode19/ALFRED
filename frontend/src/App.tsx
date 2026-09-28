import { useEffect, useState, type FormEvent } from "react";
import { ActivityTrace } from "./components/ActivityTrace";
import { ConversationLedger } from "./components/ConversationLedger";
import { OrbitalCore } from "./components/OrbitalCore";
import { useAlfred } from "./hooks/useAlfred";
import { useWakeWord } from "./hooks/useWakeWord";
import "./App.css";

const STATE_LABEL: Record<string, string> = {
  idle: "Press to speak with ALFRED",
  listening: "Listening…",
  processing: "Reading back what you said",
  thinking: "Thinking…",
  executing: "Working…",
  speaking: "Speaking…",
  error: "Something went wrong",
};

export default function App() {
  const alfred = useAlfred();
  const [textInput, setTextInput] = useState("");
  const [sheetOpen, setSheetOpen] = useState(false);
  const [clock, setClock] = useState("");

  // Wake-word is a stub for now (see hooks/useWakeWord.ts) — tapping the
  // core is the real trigger until Picovoice Porcupine is wired in.
  const wakeWord = useWakeWord({
    onWake: () => {
      if (alfred.state === "idle" || alfred.state === "error") {
        void alfred.startListening();
      }
    },
  });

  useEffect(() => {
    const tick = () => setClock(new Date().toLocaleTimeString([], { hour12: false }));
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);

  const handleCorePress = async () => {
    if (alfred.state === "idle" || alfred.state === "error") {
      await alfred.startListening();
    } else if (alfred.state === "listening") {
      await alfred.stopListeningAndSend();
    }
  };

  const handleTextSubmit = async (e: FormEvent) => {
    e.preventDefault();
    const message = textInput.trim();
    if (!message) return;
    setTextInput("");
    await alfred.sendTextMessage(message);
  };

  return (
    <div className="app-shell">
      <header className="app-shell__header">
        <p className="app-shell__brand">
          A.L.F.R.E.D. <span>· voice</span>
        </p>
        <p className="app-shell__clock">{clock}</p>
      </header>

      <main className="app-shell__stage">
        <OrbitalCore state={alfred.state} onPress={handleCorePress} />
        <p className="app-shell__state-label">{alfred.state.toUpperCase()}</p>
        <p className="app-shell__sub-label">
          {STATE_LABEL[alfred.state] ?? ""}
        </p>

        {alfred.pendingConfirmation && (
          <div className="confirm-card">
            <p>
              Run <strong>{alfred.pendingConfirmation.tool_name}</strong> with{" "}
              {JSON.stringify(alfred.pendingConfirmation.arguments)}?
            </p>
            <div className="confirm-card__actions">
              <button type="button" onClick={alfred.confirmPendingTool}>
                Confirm
              </button>
              <button type="button" onClick={alfred.declinePendingTool}>
                Cancel
              </button>
            </div>
          </div>
        )}

        {alfred.errorMessage && (
          <div className="error-banner">
            <p>{alfred.errorMessage}</p>
            <button type="button" onClick={alfred.dismissError}>
              Dismiss
            </button>
          </div>
        )}
      </main>

      <button
        type="button"
        className="app-shell__sheet-handle"
        onClick={() => setSheetOpen((v) => !v)}
        aria-expanded={sheetOpen}
        aria-controls="history-sheet"
      >
        {sheetOpen ? "Hide history" : "History"}
      </button>

      <div id="history-sheet" className={`app-shell__sheet ${sheetOpen ? "app-shell__sheet--open" : ""}`}>
        <section aria-label="Conversation history" className="app-shell__sheet-scroll">
          <ConversationLedger entries={alfred.ledger} />
        </section>

        <form onSubmit={handleTextSubmit} className="text-fallback">
          <input
            type="text"
            value={textInput}
            onChange={(e) => setTextInput(e.target.value)}
            placeholder="Or type to ALFRED…"
            aria-label="Type a message to ALFRED"
          />
          <button type="submit">Send</button>
        </form>

        <ActivityTrace trace={alfred.trace} />
      </div>
    </div>
  );
}
