# ALFRED — Phase 1: Core AI Agent

Phase 1 was where I started building the actual foundation of **ALFRED (Adaptive Language Framework for Reasoning, Execution & Dialogue)**.

The idea was to understand how an AI agent works beyond simply sending a prompt to an AI model and getting a response.

I wanted ALFRED to understand a user's request, decide whether it needed a tool, execute that tool when required and then use the result to generate a proper response.

This phase was mainly about getting the core agent architecture working.

---

##  What I Built

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

##  How It Works

The basic idea is that ALFRED doesn't need to use a tool for every request. Gemini first decides whether a tool is required.

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
 No         Yes
 ↓           ↓
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

**Example:**

```text
User:
What is 25 × 48?

        ↓

Gemini decides a calculator is needed

        ↓

Calculator Tool

        ↓

1200

        ↓

ALFRED:
"The answer is 1200."
```

This was one of the main things I wanted to get working: the model should be able to decide when to use a tool instead of relying on the LLM for everything.

---

##  Main Components

### Agent Orchestrator

This is basically the main controller of ALFRED. It manages the agent loop and handles communication between Gemini and the available tools.

### Gemini Provider

Handles communication with Google's Gemini API. I also kept the LLM provider separate so that another model provider can be integrated in the future without rewriting the entire agent.

### Tool Registry

Keeps track of the tools ALFRED has access to and manages how they are called.

### Calculator

Handles mathematical calculations without relying on unrestricted `eval()`.

### Date/Time Tool

Provides date and time information whenever the agent needs it.

---

##  Project Structure

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

##  Problems I Faced

Getting the basic agent working took some trial and error. I ran into a few issues while setting things up and testing the complete flow.

### 1. FastAPI 500 Internal Server Error

While testing the chat endpoint:

```text
POST /api/chat
```

I encountered:

```text
500 Internal Server Error
```

The server was running, but something inside the request flow was failing.

I had to trace how the request moved through FastAPI, the orchestrator and the Gemini provider to understand where things were going wrong.

### 2. Gemini 503 UNAVAILABLE Error

At times, Gemini returned:

```text
503 UNAVAILABLE
```

This happened when the model was temporarily unavailable due to high demand.

It was a useful reminder that even if the code is correct, an application can still depend on external services that aren't always available.

### 3. Gemini Function-Calling Issues

I also ran into an issue involving missing thought signatures during Gemini function-calling requests.

This was while working on the interaction between the model and the tools.

It helped me understand that tool calling isn't just about executing a function. The agent also needs to maintain the correct information throughout the interaction.

The flow looks something like this:

```text
Gemini Response
      ↓
   Tool Call
      ↓
  Tool Execution
      ↓
  Tool Result
      ↓
Gemini Response
```

### 4. Python Virtual Environment Issue

During the initial setup, I faced a PowerShell execution-policy error when trying to activate the Python virtual environment.

I had to sort out the environment configuration before I could continue running the backend.

### 5. Understanding the Agent Loop

This was probably one of the biggest learning curves in Phase 1.

Initially, understanding how the LLM, orchestrator and tools should work together took some time.

I had to understand how the model decides to call a tool, how the tool result is passed back and how the model generates the final response.

Once I understood this flow, the overall architecture started making much more sense.

---

##  What I Learned

While building Phase 1, I got hands-on experience with:

- Working with LLM APIs
- Gemini function calling
- AI agent architecture
- Tool-based AI agents
- FastAPI and backend development
- Modular Python project structure
- API error handling
- Multi-step agent execution
- Tool validation and permissions
- Writing automated tests
- Debugging AI applications

More importantly, I started understanding the difference between a normal chatbot and an AI agent that can actually use tools.

---

##  Phase 1 Status

| Component | Status |
|---|---|
| FastAPI Backend | Completed |
| Gemini Integration | Completed |
| LLM Provider Abstraction | Completed |
| Agent Orchestrator | Completed |
| Tool Registry | Completed |
| Calculator | Completed |
| Date/Time Tool | Completed |
| Function Calling | Completed |
| Agent Loop | Completed |
| Basic Testing | Completed |

---

##  What's Next?

**Phase 2 — Voice Interaction**

After getting the core agent working, the next step was to give ALFRED a voice.

Planned features included:

- Speech-to-Text
- Text-to-Speech
- Voice UI
- Conversation history
- Microphone state management
- Audio playback

---

##  What Phase 1 Meant for ALFRED

The goal of this phase wasn't to build the complete assistant straight away. It was to get the core working properly so that future features could be added without rebuilding everything from scratch.

Building this phase gave me a much better understanding of how AI agents work behind the scenes.

> **Phase 1: Build the brain before giving ALFRED a voice.**

---

**ALFRED**

**Adaptive Language Framework for Reasoning, Execution & Dialogue**

> Understand. Reason. Act.
