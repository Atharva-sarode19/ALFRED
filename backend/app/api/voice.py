"""
POST /api/voice/transcribe -- audio in, text out (STT).
POST /api/voice/synthesize -- text in, audio out (TTS).

Both sit behind the same provider-abstraction pattern as the LLM layer:
routes depend on `STTProvider`/`TTSProvider`, never on `faster-whisper` or
vendor SDKs directly.
"""

from __future__ import annotations

import logging
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.services.elevenlabs_tts_provider import ElevenLabsTTSProvider
from app.services.stt import STTError, STTProvider
from app.services.tts import TTSError, TTSProvider
from app.services.whisper_stt import WhisperSTTProvider

logger = logging.getLogger("alfred.api.voice")

router = APIRouter(prefix="/api/voice", tags=["voice"])

_MAX_AUDIO_BYTES = 25 * 1024 * 1024  # 25 MB upload cap

# ---- process-wide singletons ---------------------------------------------
_stt_provider: STTProvider | None = None
_tts_provider: TTSProvider | None = None


def get_stt_provider() -> STTProvider:
    global _stt_provider
    if _stt_provider is None:
        _stt_provider = WhisperSTTProvider()
    return _stt_provider


def get_tts_provider() -> TTSProvider:
    global _tts_provider
    if _tts_provider is None:
        _tts_provider = ElevenLabsTTSProvider()
    return _tts_provider


class TranscribeResponse(BaseModel):
    text: str
    language: str | None = None
    duration_seconds: float | None = None


class SynthesizeRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=4000)
    voice: str | None = Field(
        default=None,
        description=(
            "ElevenLabs voice ID. "
            "Omit to use the configured default."
        ),
    )


@router.get("/voices")
async def list_voices(
    tts: TTSProvider = Depends(get_tts_provider),
) -> list[dict[str, object]]:
    """List available voices from the configured speech provider."""
    try:
        return await tts.list_voices()
    except TTSError as exc:
        logger.warning("Voice listing failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error while listing TTS voices")
        raise HTTPException(status_code=502, detail="Could not retrieve available voices.") from exc


@router.post("/transcribe", response_model=TranscribeResponse)
async def transcribe(
    audio: UploadFile,
    stt: STTProvider = Depends(get_stt_provider),
) -> TranscribeResponse:
    audio_bytes = await audio.read()
    if len(audio_bytes) > _MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="Audio file is too large (max 25 MB).")

    try:
        result = await stt.transcribe(audio_bytes, filename_hint=audio.filename or "audio.webm")
    except STTError as exc:
        logger.warning("Transcription failed: %s", exc)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error during transcription")
        raise HTTPException(status_code=500, detail="Transcription failed unexpectedly.") from exc

    return TranscribeResponse(
        text=result.text, language=result.language, duration_seconds=result.duration_seconds
    )


@router.post("/synthesize")
async def synthesize(
    request: SynthesizeRequest,
    tts: TTSProvider = Depends(get_tts_provider),
) -> Response:
    try:
        result = await tts.synthesize(request.text, voice=request.voice)
    except TTSError as exc:
        logger.warning("Synthesis failed: %s", exc)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error during synthesis")
        raise HTTPException(status_code=500, detail="Speech synthesis failed unexpectedly.") from exc

    return Response(content=result.audio_bytes, media_type=result.media_type)
