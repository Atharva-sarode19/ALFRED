"""
Local Whisper implementation of `STTProvider`, via `faster-whisper`
(a CTranslate2-based reimplementation of OpenAI Whisper -- same model
weights, no API key required, runs offline).

This is the only file that should import `faster_whisper`. Everything
else depends on `STTProvider`.
"""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from pathlib import Path

from app.config.settings import Settings, get_settings
from app.services.stt import STTError, STTProvider, TranscriptionResult

logger = logging.getLogger("alfred.stt.whisper")


class WhisperSTTProvider(STTProvider):
    """
    STTProvider backed by a local `faster-whisper` model.

    The model size is configurable via `WHISPER_MODEL_SIZE` (tiny, base,
    small, medium, large-v3, ...) -- never hard-coded. The model is loaded
    lazily on first use and reused across requests.
    """

    def __init__(self, settings: Settings | None = None, model: object | None = None):
        self._settings = settings or get_settings()
        self._model = model  # allows dependency injection for tests

    def _get_model(self):
        if self._model is not None:
            return self._model
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:  # pragma: no cover
            raise STTError(
                "faster-whisper is not installed. Run `pip install faster-whisper`."
            ) from exc

        model_size = self._settings.whisper_model_size
        compute_type = self._settings.whisper_compute_type
        logger.info("Loading Whisper model '%s' (compute_type=%s)", model_size, compute_type)
        self._model = WhisperModel(model_size, compute_type=compute_type)
        return self._model

    async def transcribe(
        self, audio_bytes: bytes, *, filename_hint: str = "audio.webm"
    ) -> TranscriptionResult:
        if not audio_bytes:
            raise STTError("No audio data was provided.")

        # faster-whisper's transcribe() is a blocking, CPU/GPU-bound call --
        # run it in a thread so it doesn't block the event loop.
        return await asyncio.to_thread(self._transcribe_sync, audio_bytes, filename_hint)

    def _transcribe_sync(self, audio_bytes: bytes, filename_hint: str) -> TranscriptionResult:
        model = self._get_model()
        suffix = Path(filename_hint).suffix or ".webm"

        tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        tmp_path = tmp.name
        try:
            tmp.write(audio_bytes)
            tmp.flush()
            tmp.close()

            segments, info = model.transcribe(
                tmp_path,
                language=self._settings.whisper_language,
                vad_filter=True,
                initial_prompt=self._settings.whisper_initial_prompt,
            )
            text = " ".join(segment.text.strip() for segment in segments).strip()
        except Exception as exc:  # noqa: BLE001
            logger.exception("Whisper transcription failed")
            raise STTError(f"Transcription failed: {exc}") from exc
        finally:
            try:
                if not tmp.closed:
                    tmp.close()
            finally:
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass  # Best-effort cleanup; don't fail over a leftover temp file.

        if not text:
            raise STTError("No speech was detected in the audio.")

        return TranscriptionResult(
            text=text,
            language=getattr(info, "language", None),
            duration_seconds=getattr(info, "duration", None),
        )
