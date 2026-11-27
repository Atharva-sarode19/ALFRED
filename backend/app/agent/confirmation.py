"""
Spoken/typed confirmation handling.

`CONFIRMATION_PHRASE` is the single standard wording ALFRED uses whenever it
needs a yes or no before an action. `interpret_reply` turns the user's answer
into APPROVE, DECLINE or UNCLEAR with a deliberately conservative rule set:

- APPROVE only when EVERY word is an affirmative ("yes", "go ahead", "please
  do it"). A reply that also says anything else ("yes delete everything")
  is not an approval.
- Any negation or stop word anywhere ("no", "cancel", "wait", "don't") is a
  DECLINE, even when mixed with an affirmative ("yes... no, wait").
- Silence or an empty transcript is UNCLEAR, never approval.

Pure and dependency-free so it can be tested exhaustively.
"""

from __future__ import annotations

import re
from enum import Enum

CONFIRMATION_PHRASE = "Shall I go ahead, Sir?"

# Words that may appear around a yes/no without changing its meaning.
_FILLER = {"alfred", "hey", "sir", "um", "uh", "well", "then", "now", "thanks", "thank", "you"}

_APPROVE_WORDS = {
    "yes", "yeah", "yep", "yup", "sure", "ok", "okay", "alright", "right", "fine",
    "go", "ahead", "proceed", "do", "it", "please", "confirm", "confirmed",
    "affirmative", "absolutely", "certainly", "definitely", "of", "course", "for",
    "that", "is", "correct", "go-ahead",
}

_DECLINE_WORDS = {
    "no", "nope", "nah", "cancel", "cancelled", "stop", "dont", "never", "abort",
    "negative", "wait", "hold", "not", "nevermind", "skip", "don't",
}


class Verdict(str, Enum):
    APPROVE = "approve"
    DECLINE = "decline"
    UNCLEAR = "unclear"


def normalize(text: str) -> list[str]:
    """Lowercase words with punctuation removed ("Don't" stays one word)."""
    return re.findall(r"[a-z]+(?:['\u2019-][a-z]+)*", (text or "").lower())


def interpret_reply(text: str) -> Verdict:
    words = [w.replace("\u2019", "'") for w in normalize(text)]
    words = [w for w in words if w not in _FILLER]
    if not words:
        return Verdict.UNCLEAR

    joined = " ".join(words)
    if "never mind" in joined or "do not" in joined:
        return Verdict.DECLINE
    if "why not" in joined:
        # Ambiguous ("sure, why not" vs "why not wait?"): ask again rather than guess.
        stripped = [w for w in words if w not in ("why", "not")]
        return Verdict.DECLINE if any(w in _DECLINE_WORDS for w in stripped) else Verdict.UNCLEAR
    if any(w in _DECLINE_WORDS for w in words):
        return Verdict.DECLINE
    if len(words) <= 6 and all(w in _APPROVE_WORDS for w in words):
        return Verdict.APPROVE
    return Verdict.UNCLEAR


def is_short_reply(text: str, max_words: int = 3) -> bool:
    """A very short non-answer ("um", "hmm") that deserves one polite re-ask."""
    words = normalize(text)
    return 0 < len(words) <= max_words
