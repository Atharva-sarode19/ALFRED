# ALFRED — Phase 1

## Core AI Agent

Phase 1 is the foundation of ALFRED.

The goal was to build a basic AI agent that can understand a request, decide whether a tool is needed, use that tool, and return a response.

---

## 🎯 What I Built

Phase 1 includes:

- FastAPI backend
- Gemini AI integration
- LLM provider abstraction
- Agent orchestrator
- Tool registry
- Calculator tool
- Date/time tool
- Gemini function calling
- Basic multi-step tool execution
- Permission checks
- Execution tracing
- Automated tests

---

## 🧠 How It Works

```text
User Request
     ↓
FastAPI
     ↓
Agent Orchestrator
     ↓
Gemini
     ↓
Tool Needed?
   ↙       ↘
 No        Yes
 ↓          ↓
Answer    Tool Registry
             ↓
          Execute Tool
             ↓
          Tool Result
             ↓
           Gemini
             ↓
          Response
```

Example:

```text
User:
What is 25 × 48?

        ↓

Gemini decides that a calculator is needed

        ↓

Calculator Tool

        ↓

1200

        ↓

ALFRED:
"The answer is 1200."
```

---

## 🛠️ Main Components

### Agent Orchestrator

Controls the agent loop and manages communication between the AI model and tools.

### Gemini Provider

Handles communication with Google Gemini.

### Tool Registry

Keeps track of the tools ALFRED is allowed to use.

### Calculator

Performs mathematical calculations without using unrestricted `eval()`.

### Date/Time Tool

Provides date and time information when required.

---

## 📁 Project Structure

```text
backend/
├── app/
│   ├── agent/
│   ├── api/
│   ├── config/
│   ├── database/
│   ├── security/
│   ├── services/
│   └── tools/
│
├── tests/
├── pytest.ini
└── requirements.txt
```

---

# 🧩 Problems I Faced

Building Phase 1 was not completely straightforward. These problems helped me understand how real AI applications work.

### 1. FastAPI 500 Internal Server Error

At one point, requests to:

```text
POST /api/chat
```

returned:

```text
500 Internal Server Error
```

The FastAPI server was running, but something inside the AI request flow was failing.

I had to trace the request through the API, orchestrator, and Gemini provider to identify the problem.

---

### 2. Gemini 503 Error

Gemini sometimes returned:

```text
503 UNAVAILABLE
```

because the model was temporarily experiencing high demand.

This showed me that even if my application is working correctly, external AI services can still become temporarily unavailable.

---

### 3. Gemini Function-Calling Error

I also encountered an error related to Gemini function calling and missing thought signatures.

This happened while working with the model's tool-calling flow.

It helped me understand that an AI agent has to correctly maintain information between:

```text
AI Response
     ↓
Tool Call
     ↓
Tool Result
     ↓
AI Response
```

---

### 4. Python Virtual Environment Issue

While setting up the project, activating the virtual environment in PowerShell initially caused an execution-policy error.

I had to resolve the environment configuration before continuing development.

---

### 5. Understanding the Agent Loop

One of the biggest challenges was understanding how all the components should communicate.

The final flow became:

```text
User
 ↓
LLM
 ↓
Tool Decision
 ↓
Tool
 ↓
Tool Result
 ↓
LLM
 ↓
Final Response
```

Understanding this flow was one of the most important parts of building Phase 1.

---

## 📚 What I Learned

Through Phase 1, I learned about:

- LLM APIs
- Gemini function calling
- AI agent architecture
- Tool-based agents
- FastAPI backends
- Modular Python projects
- API error handling
- Agent loops
- Tool validation
- Testing AI systems
- Debugging AI applications

---

## 📌 Phase 1 Status

```text
FastAPI Backend       ✅
Gemini Integration    ✅
LLM Abstraction       ✅
Agent Orchestrator    ✅
Tool Registry         ✅
Calculator            ✅
Date/Time Tool        ✅
Function Calling      ✅
Agent Loop            ✅
Basic Testing         ✅
```

---

## 🚀 Next Phase

The next phase will focus on **voice interaction**.

Planned features include:

- Speech-to-Text
- Text-to-Speech
- Voice UI
- Conversation history
- Microphone state
- Audio playback

---

## 🎯 Phase 1 Goal

Phase 1 establishes the foundation for the rest of ALFRED.

The goal was not to build the final assistant immediately, but to create a solid core that future features can build upon.

> **Phase 1: Build the brain before giving ALFRED a voice.**

---

## ALFRED

**Adaptive Language Framework for Reasoning, Execution & Dialogue**

> **Understand. Reason. Act.**