# ALFRED

**Adaptive Language Framework for Reasoning, Execution & Dialogue**

> Understand. Reason. Act.

ALFRED is a personal AI assistant I'm building as an ongoing engineering project. Instead of being limited to answering questions, it can use tools, interact through voice, work with documents, manage notes and reminders, and retain information across conversations through a persistent memory system.

I started building ALFRED to explore how AI agents work beyond a simple chat interface, including how they make decisions, use tools, manage context and interact with users.

The project is being developed in phases, with each release introducing new capabilities while building on the previous ones.

---

## Features

### AI Agent
- Google Gemini integration
- Agent orchestration
- Function calling and tool selection
- Multi-step tool execution
- Tool registry
- Agent activity tracking

### Voice Interaction
- Speech-to-Text using Faster-Whisper
- Text-to-Speech
- Microphone input
- Voice-based interaction with the agent

### Tools & Integrations
- Web search
- Weather information
- Calculator
- Date and time
- Notes
- Reminders

### Document Handling
- PDF document analysis
- DOCX document analysis
- TXT file support
- File search
- Document-based information retrieval

### Persistent Memory
- PostgreSQL integration
- Short-term memory
- Long-term memory
- Task-based memory
- Memory storage and retrieval
- Context retrieval across conversations

### Interface
- React
- TypeScript
- Voice-first interface
- Interactive orb
- Conversation history
- Agent activity panel
- Tool execution status
- Permission and confirmation workflows

---

## How ALFRED Works

ALFRED uses an agent orchestration system that allows the AI to decide when a tool is required to complete a request.

When a user sends a request, the agent processes it and determines whether it can answer directly or needs to use one of its available tools. If a tool is required, the agent selects the appropriate one, executes it, processes the result and continues until it can provide a response.

Depending on the request, this may involve multiple steps and tools.

The system also includes memory retrieval, allowing relevant stored information to be used when processing new requests.

---

## Architecture

The project is divided into a frontend and a backend.

### Frontend
Built using React and TypeScript. It handles the user interface, voice interaction, displaying agent activity and communicating with the backend.

### Backend
Built using Python and FastAPI. It manages the agent orchestration, LLM communication, tool execution, voice processing, memory and other backend services.

### AI & Agent System
Google Gemini is used as the language model. The agent orchestrator manages tool selection, execution and the interaction between the model and available tools.

### Memory
PostgreSQL is used for persistent memory, allowing ALFRED to store and retrieve information across conversations.

---

## Tech Stack

| Component | Technology |
|---|---|
| Language Model | Google Gemini |
| Backend | Python, FastAPI |
| Frontend | React, TypeScript |
| Speech-to-Text | Faster-Whisper |
| Text-to-Speech | Edge TTS / configured TTS provider |
| Database | PostgreSQL |
| Local Storage | SQLite |
| Document Processing | PDF, DOCX, TXT |
| Development | Git, GitHub |

---

## Project Structure

The project is organised into separate frontend and backend components.

- `backend/` – API, agent orchestration, tools, memory and backend services
- `frontend/` – React application and user interface

The backend and frontend communicate through API endpoints.

---

## Running ALFRED

### Backend Setup

```bash
cd backend
py -3.12 -m venv .venv
```

Activate the virtual environment:

**Windows PowerShell:**

```powershell
.\.venv\Scripts\Activate.ps1
```

Install the dependencies:

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Configure the required environment variables using the provided `.env.example` file.

Start the backend:

```bash
uvicorn app.main:app --reload --port 8000
```

### Frontend Setup

```bash
cd frontend
npm install
```

Configure the frontend environment variables if required and start the development server:

```bash
npm run dev
```

---

## Development Phases

### v0.1.0 – Core AI Agent

- Gemini integration
- Agent orchestration
- Function calling
- Tool registry
- Calculator tool
- Date and time tool
- FastAPI backend
- Initial testing

### v0.2.0 – Voice Interaction

- Speech-to-Text
- Text-to-Speech
- Microphone input
- Audio playback
- Voice API endpoints
- React and TypeScript frontend
- Agent activity trace

### v0.3.0 – Real-World Tools

- Web search
- Weather
- Notes and reminders
- File search
- Document analysis
- SQLite storage
- Multi-step tool execution
- Permission and confirmation workflows
- Improved interface

### v0.4.0 – Persistent Memory System

- PostgreSQL integration
- Short-term memory
- Long-term memory
- Task-based memory
- Memory storage and retrieval
- Context retrieval across conversations
- Memory integration with the agent orchestrator
- Improved context management

---

## Current Limitations

ALFRED is still under development. Some parts of the system can be improved further, particularly memory retrieval, task execution reliability, error handling and the way the agent manages complex requests.

The project is currently focused on improving its existing architecture rather than simply adding more features.

---

## What's Next?

### Phase 5 – Agentic Workflow Engine

The next phase is focused on improving how ALFRED handles larger tasks.

Planned features include:

- Task planning and decomposition
- Multi-step workflow execution
- Task state tracking
- Error handling and recovery
- Execution checkpoints
- Human approval for important actions
- Improved execution transparency

Future development may also include Android integration, additional tools and other capabilities.

---

## About

ALFRED is an ongoing personal project developed to learn and experiment with AI agents, backend development, voice systems, tool integrations, memory systems and software engineering.

This project is continuously evolving, and new features and improvements are being added as development progresses.

**ALFRED — Adaptive Language Framework for Reasoning, Execution & Dialogue**

*Understand. Reason. Act.*
