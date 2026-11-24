import type { AlfredState } from "../types";
import "./VoiceDial.css";

interface VoiceDialProps {
  state: AlfredState;
  onPress: () => void;
}

const STATE_LABEL: Record<AlfredState, string> = {
  idle: "Press to speak",
  listening: "Listening — press to stop",
  processing: "Reading back what you said",
  thinking: "Thinking",
  executing: "Working",
  speaking: "Speaking",
  error: "Something went wrong",
};

const TICK_COUNT = 24;

export function VoiceDial({ state, onPress }: VoiceDialProps) {
  const ticks = Array.from({ length: TICK_COUNT }, (_, i) => i);

  return (
    <div className="voice-dial">
      <button
        type="button"
        className={`voice-dial__button voice-dial__button--${state}`}
        onClick={onPress}
        aria-pressed={state === "listening"}
        aria-label={STATE_LABEL[state]}
      >
        <svg viewBox="0 0 200 200" className="voice-dial__face" aria-hidden="true">
          <circle cx="100" cy="100" r="92" className="voice-dial__ring-outer" />
          {ticks.map((i) => {
            const angle = (i / TICK_COUNT) * 360;
            const isCardinal = i % 6 === 0;
            return (
              <line
                key={i}
                x1="100"
                y1={isCardinal ? "14" : "18"}
                x2="100"
                y2="24"
                className="voice-dial__tick"
                transform={`rotate(${angle} 100 100)`}
              />
            );
          })}
          <circle cx="100" cy="100" r="66" className="voice-dial__face-inner" />
          <g className="voice-dial__sweep-group">
            <circle cx="100" cy="16" r="3" className="voice-dial__sweep-dot" />
          </g>
        </svg>
        <span className="voice-dial__glyph" aria-hidden="true">
          {state === "listening" ? <ListeningGlyph /> : <MicGlyph />}
        </span>
      </button>
      <p className="voice-dial__label">{STATE_LABEL[state]}</p>
    </div>
  );
}

function MicGlyph() {
  return (
    <svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" strokeWidth="1.6">
      <rect x="9" y="2" width="6" height="12" rx="3" />
      <path d="M5 11a7 7 0 0 0 14 0" />
      <path d="M12 18v3" />
      <path d="M8 21h8" />
    </svg>
  );
}

function ListeningGlyph() {
  return (
    <svg viewBox="0 0 24 24" width="26" height="26" fill="currentColor">
      <rect x="4" y="4" width="16" height="16" rx="2.5" />
    </svg>
  );
}
