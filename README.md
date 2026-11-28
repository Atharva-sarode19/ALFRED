# ALFRED

### Adaptive Language Framework for Reasoning, Execution & Dialogue

> **Understand. Reason. Act.**

ALFRED is a personal AI assistant that I'm building as a long-term project to explore how AI assistants can go beyond answering questions and actually perform tasks using tools, memory, voice interaction and structured workflows.

The project started with a basic AI agent capable of responding to queries and using tools. Since then, I've gradually expanded it by adding voice interaction, real-world tools, persistent memory and an agentic workflow engine.

I'm building ALFRED phase-by-phase, improving its capabilities while learning more about AI agents, backend development, voice technologies, memory systems and workflow orchestration along the way.

---

## About ALFRED

ALFRED is designed to be a voice-first AI assistant that can understand user requests, interact with tools, retain information and handle tasks that involve multiple steps.

Rather than treating every request as a simple question-and-answer interaction, ALFRED is being developed to handle requests that may require planning, tool usage, information retrieval, task execution and user approval.

The goal is to gradually develop ALFRED into a more capable personal assistant while keeping its architecture modular so that new capabilities can be added without rebuilding the entire system.

---

## Features

### AI Agent
- LLM-powered responses using Gemini
- Agent orchestration
- Function calling
- Tool registry
- Multi-step tool interaction

### Voice Interaction
- Speech-to-Text using Faster-Whisper
- Text-to-Speech
- Microphone input
- Audio playback
- Voice-based interaction with the agent

### Real-World Tools
- Web search
- Weather information
- Notes and reminders
- File search
- Document analysis
- PDF, DOCX and TXT support

### Persistent Memory
- Persistent memory across conversations
- Short-term and long-term memory
- Task-related memory
- Context retrieval
- Conversation management

### Agentic Workflow Engine
- Task planning and decomposition
- Multi-step workflow execution
- Task dependencies
- Workflow validation
- Task state tracking
- Retry and failure handling
- Workflow continuation and cancellation
- Human approval checkpoints
- Persistent workflow storage

### Interface
- React and TypeScript frontend
- Voice-first interface
- Interactive ALFRED orb
- Agent activity tracking
- Workflow progress visualization
- Minimal interface focused on interaction

---

## Development Phases

ALFRED is being developed incrementally, with each phase adding a new set of capabilities.

| Version | Phase | Description |
|---|---|---|
| v0.1.0 | Phase 1 | Core AI Agent |
| v0.2.0 | Phase 2 | Voice Interaction |
| v0.3.0 | Phase 3 | Real-World Tools |
| v0.4.0 | Phase 4 | Persistent Memory System |
| v0.5.0 | Phase 5 | Agentic Workflow Engine |

### Phase 1 — Core AI Agent

The initial phase focused on building the foundation of ALFRED.

- Gemini integration
- Agent orchestration
- Function calling
- Tool registry
- Calculator tool
- Date and time tool
- FastAPI backend
- Basic testing

### Phase 2 — Voice Interaction

This phase introduced voice-based interaction, allowing ALFRED to listen to requests and respond through speech.

- Speech-to-Text
- Text-to-Speech
- Microphone input
- Audio playback
- Voice API endpoints
- React and TypeScript frontend
- Conversation history
- Agent activity trace

### Phase 3 — Real-World Tools

The third phase focused on connecting ALFRED to tools that could help it perform useful tasks beyond basic conversations.

- Web search
- Weather tool
- Notes and reminders
- File search
- Document processing
- PDF, DOCX and TXT support
- SQLite integration
- Permission and confirmation handling
- Frontend integration

### Phase 4 — Persistent Memory System

This phase focused on giving ALFRED the ability to retain information beyond individual conversations.

- PostgreSQL integration
- Short-term memory
- Long-term memory
- Task-related memory
- Memory retrieval
- Context integration
- Conversation management

### Phase 5 — Agentic Workflow Engine

The fifth phase focused on making ALFRED capable of managing tasks that require multiple steps.

Instead of handling a request through individual tool calls alone, ALFRED can create a workflow, break a task into smaller steps, organize them based on dependencies and manage their execution.

- Workflow planning
- Task decomposition
- Dependency-based execution
- Workflow validation
- Task state tracking
- Retry and failure handling
- Workflow continuation and cancellation
- Human approval checkpoints
- Persistent workflow storage
- Workflow execution history
- Activity tracing
- Workflow progress visualization

---

## Tech Stack

| Component | Technology |
|---|---|
| Backend | Python, FastAPI |
| Frontend | React, TypeScript |
| AI Model | Google Gemini |
| Speech-to-Text | Faster-Whisper |
| Text-to-Speech | Edge TTS / configured TTS provider |
| Database | PostgreSQL |
| Additional Storage | SQLite |
| Agent Architecture | Agent Orchestration, Function Calling, Tool Registry |

---

## Project Structure

ALFRED is divided into a backend and frontend to keep the agent logic separate from the user interface.

- **Backend:** Handles the agent, tool execution, memory, workflows, API endpoints and integrations.
- **Frontend:** Handles the interface, voice interaction, activity tracking and workflow visualization.
- **Database:** Stores persistent information required by ALFRED's memory and workflow systems.

---

## What's Next?

ALFRED is still an ongoing project, and there are several capabilities I want to explore in future phases.

Some of the planned improvements include:

- Vision capabilities
- Computer interaction
- Advanced automation
- Improved workflow execution
- Expanded tool integrations
- Further improvements to memory
- More advanced agent capabilities
- Additional interaction methods

These are planned directions for development and may change as the project evolves.

---

## Why I Started Building ALFRED

I started ALFRED because I wanted to understand what goes into building an AI assistant beyond simply connecting an LLM to an interface.

As the project grew, I started working with agent orchestration, tool calling, voice processing, databases, persistent memory, workflow management and frontend development. Each phase introduced new challenges and gave me an opportunity to learn something different.

ALFRED is a project that I'm continuing to build and improve as I learn more about AI and software engineering.

---

**ALFRED**

*Adaptive Language Framework for Reasoning, Execution & Dialogue*

> Understand. Reason. Act.
