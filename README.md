# ALFRED

### Adaptive Language Framework for Reasoning, Execution & Dialogue

ALFRED is a personal AI assistant project developed to understand how modern AI assistants work using **Large Language Models, AI agents, tool calling, APIs, speech processing, and frontend development**.

The project is being developed phase-by-phase, with each phase adding new capabilities to the assistant.

---

## Current Version

**v0.2.0 — Phase 2: Voice Interaction**

---

## Objectives

- Build a functional AI agent using an LLM.
- Understand LLM integration and function calling.
- Implement tool-based agent execution.
- Develop a backend using FastAPI.
- Add speech-to-text and text-to-speech capabilities.
- Build a voice-based frontend.
- Maintain conversation history and agent activity.

---

## Phase 1 — Core AI Agent

The first phase focused on building the core intelligence of ALFRED.

### Features

- Google Gemini integration
- Agent orchestration
- Function calling
- Tool registry
- Calculator tool
- Date & time tool
- FastAPI backend
- Pydantic models
- Pytest testing

### Example Workflow

```text
User
 ↓
ALFRED Agent
 ↓
Gemini
 ↓
Calculator Tool
 ↓
Result
 ↓
Final Response
