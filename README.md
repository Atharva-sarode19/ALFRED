# ALFRED

**Adaptive Language Framework for Reasoning, Execution & Dialogue**

> "Your intelligent interface to the digital world."

An agentic AI assistant: understands a request, decides whether a tool is
needed, makes a structured tool call through Google Gemini's function
calling, checks permissions, executes the tool, observes the result, and
either calls another tool or produces a final answer.

This README currently documents **Phase 1** only (Core agent: FastAPI +
Gemini abstraction + tool registry + calculator + datetime). It will grow
with each milestone (see `PHASE_1.md` for a detailed walkthrough of what
was built and why).

## Status

| Phase | Scope | Status |
|---|---|---|
| 1 | Core agent, Gemini abstraction, tool registry, calculator, datetime | ✅ done |
| 2 | Voice (STT/TTS, voice UI) | ✅ done |
| 3 | Real tools (web search, weather, notes, reminders, files) | not started |
| 4 | Memory (PostgreSQL, short/long-term, task memory) | not started |
| 5 | Agentic workflows (multi-step chaining, confirmations, traces) | partially scaffolded |
| 6 | Mobile | not started |
| 7 | Advanced (vision, computer-use) | not started |

## Architecture (Phase 1 + 2)

```text
Mic (browser)                             POST /api/chat
      |                                          |
POST /api/voice/transcribe               AgentOrchestrator  --------------------+
      |                                          |                              |
STTProvider (abstract)                   LLMProvider (abstract)                |
      |                                          |                              |
WhisperSTTProvider (faster-whisper)      GeminiProvider ---> Google Gemini API  |
                                                  |                              |
                                          ToolRegistry  <------------------------+
                                                  |
                                          calculator / datetime

Alfred's reply
      |
POST /api/voice/synthesize
      |
TTSProvider (abstract)
      |
ElevenLabsTTSProvider (ElevenLabs SDK) ---> audio bytes ---> browser playback
```

- `app/services/llm.py` — the `LLMProvider` abstraction the agent depends on.
- `app/services/gemini.py` — the only file that imports the Gemini SDK.
- `app/services/stt.py` / `whisper_stt.py` — `STTProvider` abstraction and the
  local Whisper (`faster-whisper`) implementation.
- `app/services/tts.py` / `elevenlabs_tts_provider.py` — `TTSProvider`
  abstraction and the ElevenLabs implementation.
- `app/agent/orchestrator.py` — the tool-calling loop, iteration bound,
  permission checks, and safe execution trace.
- `app/tools/` — `BaseTool`, `ToolRegistry`, and the calculator/datetime tools.
- `app/api/chat.py` — `POST /api/chat`.
- `app/api/voice.py` — `POST /api/voice/transcribe`, `POST /api/voice/synthesize`.
- `frontend/` — the voice UI (see below).

## Requirements

- Python 3.11+
- Node.js 18+ (for the frontend)
- A Gemini API key (https://ai.google.dev/)
- A browser that supports `MediaRecorder` (all evergreen browsers do) for
  the voice UI; a microphone

## Setup

```bash
cd alfred/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp ../.env.example .env   # then fill in GEMINI_API_KEY and GEMINI_MODEL
```

`.env` must set at least:

```env
GEMINI_API_KEY=your_key_here
GEMINI_MODEL=gemini-2.0-flash   # or whichever current Gemini model you have access to
```

Whisper tuning uses sensible defaults. Speech synthesis requires an ElevenLabs API key and voice ID:

```env
WHISPER_MODEL_SIZE=base          # tiny | base | small | medium | large-v3
WHISPER_COMPUTE_TYPE=int8        # int8 (CPU) | float16 (GPU) | float32
WHISPER_LANGUAGE=en              # ISO-639-1 code; blank enables auto-detect (less reliable on short clips)
WHISPER_INITIAL_PROMPT=The user's name is Atharva. This is a conversation with an AI assistant called ALFRED.
ELEVENLABS_API_KEY=your_key_here
ELEVENLABS_VOICE_ID=your_voice_id_here
```

## Run the backend

```bash
cd alfred/backend
uvicorn app.main:app --reload --port 8000
```

Then:

```bash
curl http://localhost:8000/api/health

curl http://localhost:8000/api/tools

curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What is 17% of 84000?"}'

curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What time is it in Tokyo?"}'

# Phase 2: voice endpoints
curl -X POST http://localhost:8000/api/voice/transcribe \
  -F "audio=@/path/to/a/short/recording.wav"

curl -X POST http://localhost:8000/api/voice/synthesize \
  -H "Content-Type: application/json" \
  -d '{"text": "Good evening."}' --output reply.mp3
```

The first call to `/api/voice/transcribe` will download the Whisper model
(size set by `WHISPER_MODEL_SIZE`) the first time it runs — expect a pause
on that first request.

## Run the frontend

```bash
cd alfred/frontend
npm install
cp .env.example .env    # defaults to http://localhost:8000, edit if needed
npm run dev
```

Open the printed local URL (default `http://localhost:3000`). With the
backend running on port 8000, you should be able to:

1. Press the dial to start recording (your browser will ask for
   microphone permission the first time).
2. Press it again to stop — ALFRED transcribes what you said, adds it to
   the ledger, sends it to the agent, and speaks the reply back.
3. Expand "Agent activity" at the bottom to see the safe status trace
   (tool selected, tool result, etc. — never the model's private reasoning).
4. Use the text field at the bottom instead of the mic at any time.

## Tests

Both the agent/tool tests and the new voice-route tests mock their
respective providers — no real Gemini key, no Whisper model download, and
no network access are required to run them.

```bash
cd alfred/backend
pytest
```

## Environment variables

See `.env.example` at the repo root. `GEMINI_API_KEY` and `GEMINI_MODEL`
are required; `MAX_AGENT_ITERATIONS` bounds tool-call loops (default 8);
`WHISPER_MODEL_SIZE`/`WHISPER_COMPUTE_TYPE`/`WHISPER_LANGUAGE`/`WHISPER_INITIAL_PROMPT` tune
transcription; `ELEVENLABS_API_KEY` and `ELEVENLABS_VOICE_ID` configure speech synthesis.

## Frontend design notes

The voice UI deliberately avoids the neon-hologram JARVIS look. The
concept is a bespoke instrument panel: warm graphite surfaces, an aged-brass
accent, and a muted verdigris for "listening" — like a chronometer rather
than a sci-fi HUD. The mic control is a circular dial with tick marks; the
conversation history is a numbered ledger (numbering because it's genuinely
sequential); the agent-activity trace is a collapsible strip, closer to a
status log than a dashboard widget. See `frontend/src/styles/tokens.css`
for the full palette/type scale.

## Security notes (Phase 1 + 2)

- The calculator never uses `eval()` — it walks a restricted AST and only
  allows numeric literals, a fixed operator whitelist, and a handful of
  safe math functions.
- Only tools registered in `ToolRegistry` can ever execute (allowlisting);
  unknown tool names returned by the model are rejected before anything runs.
- Tool arguments are validated against a Pydantic schema before execution;
  invalid arguments never reach a tool's `execute()`.
- The Gemini API key is read from the environment only, never hard-coded,
  never sent to the frontend.
- `docs/SECURITY.md` will expand as later phases add real network/file/
  messaging tools with MEDIUM/HIGH permission levels.
