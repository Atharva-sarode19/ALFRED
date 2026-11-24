import { useEffect, useRef, useState, type FormEvent } from "react";
import { ActivityTrace } from "./components/ActivityTrace";
import { ConversationLedger } from "./components/ConversationLedger";
import { OrbitalCore } from "./components/OrbitalCore";
import { WorkspacePanel } from "./components/WorkspacePanel";
import { useAlfred } from "./hooks/useAlfred";
import { useOrbKeyboard } from "./hooks/useOrbKeyboard";
import { OrbController } from "./orb/orbController";
import "./App.css";

const STATE_LABEL: Record<string, string> = {
  idle: "Press the orb to speak with ALFRED",
  listening: "Listening…",
  processing: "Reading back what you said",
  thinking: "Thinking…",
  executing: "Working…",
  speaking: "Speaking…",
  error: "Something went wrong",
};

export default function App() {
  // One controller shared by the orb renderer and every input that steers it.
  const controllerRef = useRef<OrbController | null>(null);
  if (controllerRef.current === null) controllerRef.current = new OrbController();
  const controller = controllerRef.current;

  const alfred = useAlfred(controller);
  const [textInput, setTextInput] = useState("");
  const [sheetOpen, setSheetOpen] = useState(false);
  const [clock, setClock] = useState("");

  useOrbKeyboard(controller, () => {
    alfred.cancelInteraction();
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
    } else {
      alfred.cancelInteraction(); // pressing the orb while it works or speaks stops it
    }
  };

  const handleTextSubmit = async (e: FormEvent) => {
    e.preventDefault();
    const message = textInput.trim();
    if (!message) return;
    setTextInput("");
    await alfred.sendTextMessage(message);
  };

  // ---- status text -----------------------------------------------------
  const headline = alfred.state.toUpperCase();
  const subline = STATE_LABEL[alfred.state] ?? "";

  return (
    <div className="app-shell">
      <header className="app-shell__header">
        <p className="app-shell__brand">
          A.L.F.R.E.D. <span>· voice</span>
        </p>
        <p className="app-shell__clock">{clock}</p>
      </header>

      <main className="app-shell__stage">
        <OrbitalCore state={alfred.state} onPress={handleCorePress} controller={controller} />
        <p className="app-shell__state-label">{headline}</p>
        <p className="app-shell__sub-label">{subline}</p>

        {alfred.pendingConfirmation && (
          <div className="confirm-card">
            <p>
              {alfred.pendingConfirmation.description ?? `Run ${alfred.pendingConfirmation.tool_name}`}. Shall I go ahead, Sir?
            </p>
            <p className="confirm-card__detail">
              {alfred.pendingConfirmation.tool_name} {JSON.stringify(alfred.pendingConfirmation.arguments)}
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

        <WorkspacePanel refreshKey={alfred.refreshKey} />

        <ActivityTrace trace={alfred.trace} />
      </div>
    </div>
  );
}
