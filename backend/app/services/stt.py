"""
Speech-to-text abstraction.

Like the LLM layer, STT sits behind an interface so the concrete engine
(local Whisper today, a hosted API tomorrow) can be swapped without
touching the agent, the API routes, or the frontend contract.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


class STTError(RuntimeError):
    """Raised when transcription fails (bad audio, engine unavailable, etc.)."""


@dataclass
class TranscriptionResult:
    text: str
    language: str | None = None
    duration_seconds: float | None = None


class STTProvider(ABC):
    """Abstract speech-to-text engine."""

    @abstractmethod
    async def transcribe(self, audio_bytes: bytes, *, filename_hint: str = "audio.webm") -> TranscriptionResult:
        """
        Transcribe raw audio bytes to text.

        `filename_hint` carries the original extension/mimetype hint (e.g.
        "recording.webm", "recording.wav") so providers that dispatch on
        file type can decode correctly.
        """
        raise NotImplementedError
