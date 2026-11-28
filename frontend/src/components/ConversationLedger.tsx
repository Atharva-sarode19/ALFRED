import type { LedgerEntry } from "../types";
import ReactMarkdown from "react-markdown";
import "./ConversationLedger.css";

interface ConversationLedgerProps {
  entries: LedgerEntry[];
}

const ROLE_LABEL: Record<LedgerEntry["role"], string> = {
  user: "You",
  alfred: "Alfred",
  system: "Note",
};

export function ConversationLedger({ entries }: ConversationLedgerProps) {
  if (entries.length === 0) {
    return (
      <div className="ledger ledger--empty">
        <p>Nothing said yet. Press the dial and ask ALFRED something.</p>
      </div>
    );
  }

  return (
    <ol className="ledger">
      {entries.map((entry, index) => (
        <li key={entry.id} className={`ledger__entry ledger__entry--${entry.role}`}>
          <span className="ledger__index">{String(index + 1).padStart(3, "0")}</span>
          <div className="ledger__body">
            <span className="ledger__role">{ROLE_LABEL[entry.role]}</span>
            <div className="ledger__text">
              <ReactMarkdown>{entry.text}</ReactMarkdown>
            </div>
          </div>
        </li>
      ))}
    </ol>
  );
}
