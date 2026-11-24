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
| 3 | Real tools (web search, weather, notes, reminders, files) | ✅ done |
| 4 | Memory (PostgreSQL, short/long-term, task memory) | not started |
| 5 | Agentic workflows (multi-step chaining, confirmations, traces) | partially done (confirmations, bounded loops, traces) |
| 6 | Mobile | not started |
| 7 | Advanced (vision, computer-use) | not started |
| 0.3.0 | Enlarged orb with drag-to-rotate, "Shall I go ahead, Sir?" | ✅ done |

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
- Phase 3 (see `docs/PHASE_3.md`): `app/tools/{web_search,weather,notes,reminders,file_search,document_analyzer}.py`,
  `app/database/sqlite_store.py`, `app/services/{documents,search,ddg_search}.py`,
  `app/security/untrusted.py`, `app/api/{files,reminders,deps}.py`, and `POST /api/chat/confirm`.

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

### Orb controls (0.3.0)

| Input | Action |
|---|---|
| Mouse / trackpad | Click the orb = talk, drag the orb = rotate it (automatic spin pauses while you hold it), wheel = resize |
| Keyboard | Arrows rotate, `+` / `-` resize, `P` pause, `0` reset, `Esc` cancel (stops listening, speaking or waiting; declines a pending action) |

When an action needs approval, ALFRED says "Shall I go ahead, Sir?" and listens
for "yes", "go ahead", "no", "cancel" and similar. Cancelling is always possible; nothing but your spoken or clicked answer approves.

## Tools (Phase 3)

| Tool | What it does | Permission |
|---|---|---|
| `calculator` | Safe arithmetic (AST parser, never `eval`) | LOW |
| `datetime` | Current time, timezone conversion, date math | LOW |
| `web_search` | Web search via DuckDuckGo (`ddgs`): titles, URLs, snippets | LOW |
| `weather` | Current conditions and forecast via Open-Meteo (no key) | LOW |
| `notes` | create / get / search / delete | get, search LOW; create MEDIUM; delete HIGH |
| `reminders` | create / list / delete (stored in UTC, shown in your timezone) | list LOW; create, delete MEDIUM |
| `file_search` | Find uploaded documents by name and content (SQLite FTS5) | LOW |
| `document_analyzer` | Read an uploaded PDF/DOCX/TXT in pages, or fetch passages for a topic | LOW |

Permissions are checked per action. HIGH actions always ask first; MEDIUM
actions ask unless `REQUIRE_MEDIUM_CONFIRMATION=false`. When the agent needs a
yes or no it pauses, the UI shows the exact call, and `POST /api/chat/confirm`
runs (or declines) that stored call. The client cannot pre-approve anything.

Documents: upload from the Workspace panel in the history sheet, or
`POST /api/files/upload` (PDF, DOCX, TXT). Then ask, for example, "summarize the
file I just uploaded". Scanned or image-only PDFs have no text layer and are rejected.

Set `DEFAULT_TIMEZONE` (for example `Asia/Kolkata`) so "tomorrow at 9am" means your 9am.

Known limits: `web_search` returns snippets only (no page fetching yet); the
DuckDuckGo backend is an unofficial scraper that can be rate-limited
(`SearchProvider` is the seam for swapping in another engine); reminders are
stored and listed but nothing notifies you when one comes due; there is no
authentication yet, so keep the server on localhost.

## Tests

Both the agent/tool tests and the new voice-route tests mock their
respective providers — no real Gemini key, no Whisper model download, and
no network access are required to run them.

```bash
cd alfred/backend
pytest

cd ../frontend
npm test          # orb controller and drag, silence detector, audio level (Node 22+)
```

## Environment variables

See `.env.example` at the repo root. `GEMINI_API_KEY` and `GEMINI_MODEL`
are required; `MAX_AGENT_ITERATIONS` bounds tool-call loops (default 8);
`WHISPER_MODEL_SIZE`/`WHISPER_COMPUTE_TYPE`/`WHISPER_LANGUAGE`/`WHISPER_INITIAL_PROMPT` tune
transcription; `ELEVENLABS_API_KEY` and `ELEVENLABS_VOICE_ID` configure speech synthesis;
`DEFAULT_TIMEZONE`, `REQUIRE_MEDIUM_CONFIRMATION`, `ALFRED_DATA_DIR`, `MAX_UPLOAD_MB` and
`SEARCH_MAX_RESULTS` configure the Phase 3 tools.

## Frontend design notes

The voice UI deliberately avoids the neon-hologram JARVIS look. The
concept is a bespoke instrument panel: warm graphite surfaces, an aged-brass
accent, and a muted verdigris for "listening" — like a chronometer rather
than a sci-fi HUD. The mic control is a circular dial with tick marks; the
conversation history is a numbered ledger (numbering because it's genuinely
sequential); the agent-activity trace is a collapsible strip, closer to a
status log than a dashboard widget. See `frontend/src/styles/tokens.css`
for the full palette/type scale.

## Security notes (Phase 1 to 3)

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
- Web results and document text are wrapped in untrusted-content markers
  before the model sees them, and the system prompt tells the model to treat
  them as data, never instructions. This reduces prompt-injection risk; it
  cannot eliminate it, which is why side-effecting tools ask for confirmation.
- Confirmations are server-side state, not a client flag (the old
  `auto_approve_confirmations` request field was removed).
- Uploads are validated by size, extension and content signature, stored under
  generated names, and DOCX files containing XML DTDs are rejected.
