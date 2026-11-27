# ALFRED

### Adaptive Language Framework for Reasoning, Execution & Dialogue

**"Understand. Reason. Act."**

## About

ALFRED is an AI-powered voice assistant that I built with the idea of having my own personal AI assistant. It is inspired by fictional assistants like Alfred from Batman and JARVIS from Iron Man.

The main idea behind ALFRED is to make an assistant that can do more than just answer questions. It can understand what the user asks, decide what needs to be done, use different tools, and provide a response through text or voice.

ALFRED uses Google Gemini as its AI model and has a separate backend and frontend to handle its different functions.

## Features

**AI Assistant**
- Answers questions using Google Gemini.
- Understands user requests and follow-up questions.
- Maintains conversation context.
- Selects tools based on what the user asks.
- Handles tasks that require multiple steps.

**Voice Interaction**
- Speech-to-Text using Faster-Whisper.
- Text-to-Speech for spoken responses.
- Microphone input and audio playback.
- Voice interaction through the interface.

**Tools**
- Web search using DuckDuckGo.
- Weather information using Open-Meteo.
- Calculator for mathematical operations.
- Date and time information.
- Create, search, retrieve, and delete notes.
- Create, list, and delete reminders.
- Search uploaded files.
- Read and analyse PDF, DOCX, and TXT documents.

**Other Features**
- Agent activity panel to show what ALFRED is doing.
- Tool calling using Gemini.
- Permission checks before tool execution.
- Multi-step task handling.
- SQLite storage for notes, reminders, and document information.
- Interactive animated orb that rotates with cursor movement.

## How It Works

ALFRED uses Google Gemini to understand the user's request and decide what to do next.

For example, if someone asks ALFRED to search for something, it selects the web search tool, gets the results, and uses them to prepare an answer.

The basic process looks like this:

```text
       User
        |
        v
   Voice / Text
        |
        v
  ALFRED Backend
        |
        v
 Agent Orchestrator
        |
        v
    Gemini API
        |
        v
   Tool Selection
        |
        v
  Tool Execution
        |
        v
   Tool Results
        |
        v
 Final Response
        |
        v
   Voice / Text
```

If a request needs more than one tool, ALFRED can use multiple steps before giving the final answer.

## Technologies Used

| Component | Technology |
|---|---|
| Backend | Python, FastAPI |
| Frontend | React, TypeScript |
| AI Model | Google Gemini API |
| Speech-to-Text | Faster-Whisper |
| Text-to-Speech | TTS integration |
| Database | SQLite |
| Web Search | DuckDuckGo |
| Weather | Open-Meteo |
| Version Control | Git, GitHub |

## Main Components

- **Agent Orchestrator:** Handles user requests and manages the steps needed to complete them.
- **Gemini Integration:** Helps ALFRED understand requests and decide which tools to use.
- **Tool Registry:** Keeps all available tools organised.
- **Voice System:** Handles voice input and spoken responses.
- **Database:** Stores information used by notes, reminders, and document features.
- **Frontend:** Provides the interface for interacting with ALFRED.

## Example Commands

Here are a few examples of what you can ask ALFRED:

| You can ask | ALFRED can |
|---|---|
| What is 25 × 42? | Calculate the answer |
| Search for recent AI news. | Search the web |
| What's the weather in Pune? | Get weather information |
| What time is it in Tokyo? | Get the current time |
| Create a note about my project. | Save a note |
| Show my reminders. | Retrieve reminders |
| Find my project report. | Search uploaded files |
| Summarise this PDF. | Analyse the document |

## Project Structure

ALFRED has two main parts: the backend, which handles the main functionality, and the frontend, which provides the user interface.

```text
ALFRED/
│
├── backend/
│   ├── app/
│   │   ├── agent/
│   │   ├── tools/
│   │   ├── services/
│   │   ├── database/
│   │   ├── api/
│   │   └── security/
│   │
│   └── tests/
│
├── frontend/
│   └── src/
│       ├── components/
│       ├── pages/
│       ├── services/
│       └── hooks/
│
├── .env.example
├── .gitignore
└── README.md
```

## Getting Started

### Requirements

- Python
- Node.js and npm
- Google Gemini API key
- Git

### Environment Setup

Create a `.env` file in the backend and add your Gemini API details.

```env
GEMINI_API_KEY=your_api_key
GEMINI_MODEL=your_model_name
```

Keep your API key private. Do not upload your `.env` file to GitHub.

Install the required dependencies in the backend and frontend, then follow the setup instructions in the repository to run ALFRED.

## Security

ALFRED includes a permission system to control how tools are used.

- Checks tool inputs before execution.
- Requires confirmation for sensitive actions.
- Keeps API keys in environment variables.
- Treats external information as untrusted content.
- Does not allow unrestricted system command execution.
- Shows activity status without exposing the model's private reasoning.

## Future Scope

Some areas where ALFRED can be expanded include:

- Better memory and conversation handling.
- More tools and integrations.
- Android and iOS applications.
- Image and vision capabilities.
- Computer interaction with user approval.
- More task automation features.

## Project Details

**Project Name:** ALFRED

**Full Form:** Adaptive Language Framework for Reasoning, Execution & Dialogue

**AI Model:** Google Gemini

**Backend:** Python and FastAPI

**Frontend:** React and TypeScript

**GitHub:** [Atharva-sarode19/ALFRED](https://github.com/Atharva-sarode19/ALFRED)

---

**ALFRED — Understand. Reason. Act.**
