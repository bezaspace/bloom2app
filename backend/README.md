# Bloom2 Backend

FastAPI + Google ADK + Gemini Live API backend for the Bloom2 voice assistant.

Streams bidirectional audio between the mobile client and Gemini's Live API over
a WebSocket, using ADK's `Runner.run_live()` for agent orchestration.

## Setup

```bash
cd backend
uv sync
```

Add your Gemini API key to `.env` (get one at https://aistudio.google.com/apikey):

```
GOOGLE_API_KEY=your_key_here
```

## Run

```bash
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Health check: `GET http://localhost:8000/health`
New session:  `GET http://localhost:8000/new-session`
WebSocket:    `ws://localhost:8000/ws/{user_id}/{session_id}`
