# Phase 2 — Voice Interaction

Phase 2 adds speech-to-text, text-to-speech, and a voice-first frontend on
top of the unchanged Phase 1 agent. No Phase 1 file (orchestrator, tool
registry, calculator, datetime, Gemini provider, `POST /api/chat`) was
modified to build this — voice is purely additive.

## What was added

| Layer | File(s) | Notes |
|---|---|---|
| STT abstraction | `app/services/stt.py` | `STTProvider` ABC, same shape as `LLMProvider` |
| STT implementation | `app/services/whisper_stt.py` | Local `faster-whisper`; no API key; model loads lazily on first use |
| TTS abstraction | `app/services/tts.py` | `TTSProvider` ABC |
| TTS implementation | `app/services/edge_tts_provider.py` | `edge-tts`; no API key, **but requires live network access** to Microsoft's endpoint — not a fully offline path the way Whisper is |
| API | `app/api/voice.py` | `POST /api/voice/transcribe` (audio → text), `POST /api/voice/synthesize` (text → audio) |
| Config | `app/config/settings.py` | Added `whisper_model_size`, `whisper_compute_type`, `tts_voice` — additive properties, nothing existing changed |
| Frontend | `frontend/` | Voice dial, conversation ledger, collapsible agent-activity trace, `useVoiceRecorder`/`useAlfred` hooks |

## Design decisions

- **Same provider-abstraction pattern as the LLM layer.** The agent and API
  routes depend on `STTProvider`/`TTSProvider`, never on `faster_whisper` or
  `edge_tts` directly — swapping either engine later (a hosted STT API, a
  cloned-voice TTS provider) means writing one new class and pointing
  `get_stt_provider()`/`get_tts_provider()` at it.
- **Voice states map onto Section 11's state machine** (`idle → listening →
  processing → thinking → executing → speaking → error`), driven from
  `useAlfred.ts` on the frontend rather than invented ad hoc.
- **A TTS failure never blocks the text answer.** If synthesis fails, the
  reply still lands in the conversation ledger — voice playback degrades
  gracefully instead of hiding a working answer behind a broken audio call.

## Environment variables (additive — all optional, all have defaults)

```env
WHISPER_MODEL_SIZE=base          # tiny | base | small | medium | large-v3
WHISPER_COMPUTE_TYPE=int8        # int8 (CPU) | float16 (GPU) | float32
TTS_VOICE=en-US-GuyNeural        # any edge-tts voice; list with `edge-tts --list-voices`
```

## Known operational notes

- **`edge-tts` is not offline.** Despite requiring no API key, it calls
  Microsoft's endpoint under the hood. STT (Whisper) works with no network
  once the model is downloaded; TTS does not. Worth knowing before
  deploying anywhere network-restricted.
- **`ctranslate2` (a `faster-whisper` dependency) ships precompiled
  wheels** and has occasionally lagged behind very recent Python releases.
  Confirm `pip install -r requirements.txt` succeeds cleanly on your actual
  Python version before relying on this in CI or on a new machine.
- **First `/api/voice/transcribe` call downloads the Whisper model** (size
  per `WHISPER_MODEL_SIZE`) — expect a one-time pause on first use, not a
  bug.

## Tests

`tests/test_voice_api.py` mocks both providers via FastAPI's
`app.dependency_overrides`, the same pattern the Phase 1 orchestrator tests
use for the LLM provider — no real Gemini key, Whisper model download, or
network access required to run the suite.

```bash
cd backend
pytest -v
```

## Explicitly out of scope for Phase 2

Per the master spec, the following are deferred and were **not** built here:
wake-word detection (push-to-talk only, per Section 12), memory persistence
(Phase 4), real tools beyond calculator/datetime (Phase 3), and any
proactive/unprompted behavior (Phase 7).
