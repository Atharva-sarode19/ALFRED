# Phase 3 — Real Tools

Phase 3 gives the agent six real tools, persistence for them, and document
upload, on top of the Phase 1 agent and Phase 2 voice UI. Unlike Phase 2 it is
**not** purely additive: per-action permissions and a working confirmation flow
required changes to the orchestrator, registry and chat API.

## What was added

| Layer | File(s) | Notes |
|---|---|---|
| Tools | `app/tools/web_search.py`, `weather.py`, `notes.py`, `reminders.py`, `file_search.py`, `document_analyzer.py` | All registered in `build_default_registry()`; the orchestrator did not need to learn about any of them |
| Search abstraction | `app/services/search.py`, `ddg_search.py` | `SearchProvider` ABC + DuckDuckGo (`ddgs`) implementation; the only file importing `ddgs` |
| Persistence | `app/database/sqlite_store.py` | SQLite (notes, reminders, files, chunked full-text index). No Pydantic/FastAPI imports; Phase 4 swaps it for PostgreSQL with the same method names |
| Documents | `app/services/documents.py` | Upload validation, PDF (`pypdf`), DOCX (stdlib zip+XML) and TXT extraction, chunking |
| Untrusted content | `app/security/untrusted.py` | Wraps web/document content in markers the system prompt refers to |
| API | `app/api/files.py`, `reminders.py`, `deps.py` | `POST /api/files/upload`, `GET /api/files`, `POST /api/files/search`, `GET/POST /api/reminders`, `DELETE /api/reminders/{id}`; `deps.py` holds the shared singletons (store, registry, LLM, sessions) |
| Confirmation | `app/api/chat.py` | New `POST /api/chat/confirm` |
| Frontend | `components/WorkspacePanel.tsx/.css`, `services/api.ts`, `hooks/useAlfred.ts`, `App.tsx`, `types.ts` | Upload documents and see upcoming reminders from the history sheet; confirm/decline calls the new endpoint |

## Existing files that changed

| File | Change |
|---|---|
| `app/agent/orchestrator.py` | Loop rewritten around pause/resume. Your persona ("sir"), spoken-text rule and the per-error messages (auth, rate limit, overloaded, bad request) are kept verbatim; the system prompt now also carries the current date/time, untrusted-content rules and tool guidance |
| `app/agent/state.py` | `PendingAction`; history trimming never starts mid tool exchange; `SessionStore.get()` |
| `app/tools/base.py` | `BaseTool.permission_for(arguments)`; `ToolResult.untrusted` |
| `app/tools/registry.py` | `permission_for_call`, `requires_confirmation(name, args, confirm_medium=)`, `build_default_registry(settings, store)` builds all eight tools |
| `app/services/gemini.py` | Only `_to_gemini_contents`: consecutive tool results are merged into one user turn (Gemini expects all responses to parallel calls together). Retries, error mapping, thought signatures and schema cleaning are untouched |
| `app/api/chat.py` | `auto_approve_confirmations` removed; singletons moved to `deps.py` |
| `app/config/settings.py` | Additive properties only |
| `app/main.py` | New routers; version 0.3.0 |
| `requirements.txt`, `.env.example`, `.gitignore`, `README.md` | New deps and variables; `data/` ignored so uploads are never committed |
| `tests/test_orchestrator.py`, `tests/test_registry.py` | See Tests |

## Design decisions

- **Permissions are per action, not per tool.** Reading a note is LOW, creating
  is MEDIUM, deleting a note is HIGH (permanent data loss). `permission_level`
  on a tool stays its highest level, for listings.
- **Confirmation is server-side state.** When a call needs approval the loop
  pauses and stores the exact call (plus any calls queued behind it).
  `resume()` runs or declines *that* call. The previous design re-ran the whole
  turn with `auto_approve_confirmations=true`: the model could produce
  different arguments the second time, it approved every pending call
  including HIGH ones, and the first pause left an unanswered function call in
  history that broke the next request. A new user message abandons a pending
  action and closes it out in history.
- **External content is data.** `web_search`, `file_search` and
  `document_analyzer` mark results `untrusted`; the orchestrator wraps them and
  neutralizes any attempt to forge the closing marker. This lowers injection
  risk; it does not remove it.
- **Reminders need the current time.** The system prompt now includes the
  current date/time in `DEFAULT_TIMEZONE`. Times are stored in UTC, shown
  local, and past times are rejected (catches a model using the wrong year).
- **A confirmation question is spoken**, not only shown, so voice use does not
  require looking at the screen.
- **SQLite now, PostgreSQL in Phase 4.** `ALFRED_DATA_DIR` holds the database
  and uploads; `DATABASE_URL` is reserved and ignored for now.

## Environment variables (additive, all optional)

```env
REQUIRE_MEDIUM_CONFIRMATION=true
DEFAULT_TIMEZONE=UTC             # e.g. Asia/Kolkata
ALFRED_DATA_DIR=./data
MAX_UPLOAD_MB=20
SEARCH_MAX_RESULTS=5
```

## Known operational notes

- **`web_search` scrapes DuckDuckGo** through an unofficial package and can be
  rate-limited. It returns snippets only; there is no page fetching yet.
- **Scanned PDFs are rejected** (no text layer; OCR is out of scope).
- **No notification when a reminder comes due.** Reminders are stored and
  listed; delivery needs the Phase 5/7 scheduler.
- **No authentication yet.** Anyone who can reach the server can read uploaded
  documents. Keep it on localhost until the security phase.

## Tests

New: `test_sqlite_store.py`, `test_documents.py`, `test_phase3_tools.py`,
`test_confirmation_flow.py`, `test_gemini_contents.py`. Updated:
`test_registry.py` (full registry, per-action permissions, Gemini-safe schemas)
and `test_orchestrator.py` (uses a calculator+datetime registry so it touches no
database; one assertion changed, see below). All use fakes: no Gemini key,
network, or model downloads.

```bash
cd backend
pytest -v
```

`test_auth_error_gives_a_distinct_configuration_message` asserted that the
auth-failure reply does not contain "retry", but that reply says the problem is
"not something you can retry". The assertion now checks for "try again".

Verification status when this was written: the store, document, tool,
confirmation-flow and orchestrator tests were executed against stand-ins for
Pydantic, pytest and the Google SDK (the sandbox had no network), 87 passing.
Not executed: `test_voice_api.py` (needs FastAPI), `test_gemini_contents.py`
and the schema test against the real SDK, PDF extraction, live Gemini,
DuckDuckGo and Open-Meteo calls, and `npm install` / `vite build`.

## Explicitly out of scope for Phase 3

Memory and PostgreSQL (Phase 4), authentication and rate limiting (security
phase), fetching full web pages, OCR, reminder delivery, and file deletion.
