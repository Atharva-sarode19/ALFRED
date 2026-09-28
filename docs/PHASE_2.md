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
