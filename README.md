# ALFRED

### Adaptive Language Framework for Reasoning, Execution & Dialogue

ALFRED is a personal AI assistant project built to explore **LLMs, AI agents, tool calling, voice interaction, and frontend development**.

The project is developed phase-by-phase, with each phase adding new capabilities while building on the previous system.

## Current Version

**v0.2.0 — Phase 2: Voice Interaction**

## Phase 1 — Core AI Agent

The first phase focused on building the core AI agent and its tool-based execution system.

* Google Gemini integration
* Agent orchestration
* Function calling
* Tool registry
* Calculator tool
* Date & time tool
* FastAPI backend
* Pytest testing

Phase 1 established the main agent architecture, allowing ALFRED to process requests and use tools when required.

## Phase 2 — Voice Interaction

Phase 2 adds a voice interface to the existing ALFRED agent.

* Speech-to-text using `faster-whisper`
* Text-to-speech using Edge TTS
* Microphone input and audio playback
* Voice API endpoints
* React + TypeScript frontend
* Conversation history
* Agent activity trace
* Voice states: `IDLE`, `LISTENING`, `THINKING`, `EXECUTING`, `SPEAKING`

The main goal of Phase 2 is to allow users to **speak with ALFRED and receive spoken responses** while continuing to use the same agent and tools from Phase 1.

## System Flow

```text
Voice Input
     ↓
Speech-to-Text
     ↓
ALFRED Agent
     ↓
Gemini + Tools
     ↓
Response
     ↓
Text-to-Speech
     ↓
Voice Output
```

## Tech Stack

* **Backend:** Python, FastAPI, Pydantic
* **LLM:** Google Gemini
* **STT:** faster-whisper
* **TTS:** Edge TTS
* **Frontend:** React, TypeScript, Vite
* **Testing:** Pytest
* **Version Control:** Git & GitHub

## Roadmap

* [x] Phase 1 — Core AI Agent
* [x] Phase 2 — Voice Interaction
* [ ] Phase 3 — Real-World Tools
* [ ] Phase 4 — Memory
* [ ] Phase 5 — Automation
* [ ] Phase 6 — Mobile
* [ ] Phase 7 — Advanced Capabilities

## License

This project is licensed under the **MIT License**.
