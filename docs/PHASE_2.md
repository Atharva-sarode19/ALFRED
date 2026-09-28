````markdown
# ALFRED — Phase 2

## Voice Interaction

Phase 2 extends the foundation built in Phase 1 by giving ALFRED a voice interface.

The goal was to allow a user to speak to ALFRED, convert the speech into text, process it through the existing AI agent, and return the response as audio.

---

## 🎯 What I Built

Phase 2 includes:

- Speech-to-Text using `faster-whisper`
- Text-to-Speech using Edge TTS
- FastAPI voice APIs
- Microphone recording
- Audio playback
- React + TypeScript frontend
- Voice-first UI
- Conversation history
- Agent activity trace
- Microphone state management
- Voice states
- Integration with the Phase 1 agent

---

## 🧠 How It Works

```text
User Speaks
     ↓
Microphone
     ↓
Speech-to-Text
     ↓
Recognized Text
     ↓
ALFRED Agent
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
             ↓
        Text-to-Speech
             ↓
        Audio Output
             ↓
            User
````

Example:

```text
User:
"What is 25 × 48?"

        ↓

Voice is converted to text

        ↓

ALFRED sends the request to Gemini

        ↓

Calculator Tool

        ↓

1200

        ↓

ALFRED generates the response

        ↓

Edge TTS converts it to speech

        ↓

ALFRED:
"The answer is 1200."
```

---

## 🛠️ Main Components

### Speech-to-Text

Uses `faster-whisper` to convert the user's microphone input into text.

### Voice API

Provides endpoints for processing audio and generating speech through the FastAPI backend.

### Text-to-Speech

Uses Edge TTS to convert ALFRED's response into playable audio.

### Voice UI

A React + TypeScript interface handles microphone input, assistant states, conversation history, and audio playback.

### Agent Integration

The existing Phase 1 agent is reused for processing requests instead of creating a separate voice-specific agent.

---

## 📁 Project Structure

```text
frontend/
├── src/
│   ├── components/
│   ├── hooks/
│   ├── services/
│   └── App.tsx/

backend/
├── app/
│   ├── api/
│   ├── agent/
│   ├── services/
│   └── main.py
│
├── tests/
├── pytest.ini
└── requirements.txt
```

---

# 🧩 Problems I Faced

Building Phase 2 introduced a new set of challenges because the frontend, backend, speech services, and AI agent all had to work together.

### 1. Frontend–Backend Communication

The backend APIs were working, but the frontend initially failed to communicate with the correct backend endpoint.

I had to check the API base URL, request format, response fields, and CORS configuration.

---

### 2. Connecting Voice to the Existing Agent

The main challenge was making sure the speech pipeline connected correctly to the Phase 1 agent.

The final flow became:

```text
Voice
 ↓
STT
 ↓
Phase 1 Agent
 ↓
Gemini + Tools
 ↓
Response
 ↓
TTS
 ↓
Voice
```

This allowed Phase 2 to build on the existing agent instead of duplicating the core logic.

---

### 3. Microphone and Audio Handling

Working with browser microphone access and audio playback required handling different states during recording, processing, and playback.

The interface needed to clearly represent what ALFRED was doing at each stage.

---

### 4. Voice State Management

I had to coordinate the different states of the assistant:

```text
IDLE
 ↓
LISTENING
 ↓
THINKING
 ↓
EXECUTING
 ↓
SPEAKING
 ↓
IDLE
```

Keeping these states synchronized with the actual backend process was an important part of Phase 2.

---

## 📚 What I Learned

Through Phase 2, I learned about:

* Speech-to-Text systems
* Text-to-Speech systems
* Microphone APIs
* Audio processing
* FastAPI voice endpoints
* React state management
* Frontend/backend communication
* Voice UI design
* Connecting speech with an AI agent
* Testing voice APIs
* Handling asynchronous operations

---

## 📌 Phase 2 Status

```text
Speech-to-Text        ✅
Text-to-Speech        ✅
Voice API             ✅
Microphone Input      ✅
Audio Playback        ✅
React Frontend        ✅
Conversation History  ✅
Agent Activity        ✅
Voice States          ✅
Phase 1 Integration   ✅
Basic Testing         ✅
```

---

## 🚀 Next Phase

The next phase will focus on **real-world tools**.

Planned capabilities include:

* Web search
* Weather
* File interaction
* External APIs
* Additional utility tools

---

## 🎯 Phase 2 Goal

Phase 2 transforms ALFRED from a mainly text-based AI agent into a basic voice-enabled assistant.

The goal was to build the voice layer while keeping the Phase 1 agent as the core intelligence.

> **Phase 2: Give ALFRED a voice without rebuilding its brain.**

---

## ALFRED

**Adaptive Language Framework for Reasoning, Execution & Dialogue**

> **Understand. Reason. Act.**

```
```
