import { useCallback, useEffect, useRef, useState } from "react";
import { ActivityPanel } from "./components/ActivityPanel";
import { ControlBar, type PanelId } from "./components/ControlBar";
import { MemoryIndicator } from "./components/MemoryIndicator";
import { TextComposer } from "./components/TextComposer";
import { ConversationLedger } from "./components/ConversationLedger";
import { OrbitalCore } from "./components/OrbitalCore";
import { WorkspacePanel } from "./components/WorkspacePanel";
import { useAlfred } from "./hooks/useAlfred";
import { useMemoryStatus } from "./hooks/useMemoryStatus";
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
  const [panel, setPanel] = useState<PanelId | null>(null);
  const [clock, setClock] = useState("");
  const memory = useMemoryStatus(alfred.refreshKey, alfred.recallKey);

  const panelRef = useRef<PanelId | null>(null);
  panelRef.current = panel;
  const closePanel = useCallback(() => setPanel(null), []);
  const togglePanel = useCallback((id: PanelId) => setPanel((open) => (open === id ? null : id)), []);
  const sheetOpen = panel === "history";

  // Escape closes an open panel first; it only cancels the running interaction when none is open.
  useOrbKeyboard(controller, () => {
    if (panelRef.current) return;
    alfred.cancelInteraction();
  });

  useEffect(() => {
    if (!panel) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") closePanel();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [panel, closePanel]);

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

  // ---- status text -----------------------------------------------------
  const headline = alfred.state.toUpperCase();
  const subline = STATE_LABEL[alfred.state] ?? "";

  return (
    <div className={`app-shell ${alfred.pendingConfirmation || alfred.errorMessage ? "app-shell--prompt" : ""}`}>
      <header className="app-shell__header">
        <p className="app-shell__brand">
          A.L.F.R.E.D. <span>· voice</span>
        </p>
        <div className="app-shell__meta">
          <MemoryIndicator indicator={memory.indicator} />
          <p className="app-shell__clock">{clock}</p>
        </div>
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

      {panel && <div className="app-shell__backdrop" onClick={closePanel} aria-hidden="true" />}

      <ControlBar open={panel} onToggle={togglePanel} attention={alfred.pendingConfirmation !== null} />

      <TextComposer open={panel === "text"} onSend={alfred.sendTextMessage} onClose={closePanel} />

      <ActivityPanel
        open={panel === "activity"}
        events={alfred.activity}
        busy={alfred.state === "thinking"}
        pending={alfred.pendingConfirmation}
        onApprove={alfred.confirmPendingTool}
        onReject={alfred.declinePendingTool}
        onClose={closePanel}
      />

      <div
        id="history-sheet"
        className={`app-shell__sheet ${sheetOpen ? "app-shell__sheet--open" : ""}`}
        aria-hidden={!sheetOpen}
      >
        <button type="button" className="app-shell__sheet-close" onClick={closePanel} aria-label="Close history">
          <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" focusable="false">
            <path d="M3 3l10 10M13 3L3 13" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
        </button>
        <section aria-label="Conversation history" className="app-shell__sheet-scroll">
          <ConversationLedger entries={alfred.ledger} />
        </section>

        <WorkspacePanel refreshKey={alfred.refreshKey} memory={memory.status} />
      </div>
    </div>
  );
}
