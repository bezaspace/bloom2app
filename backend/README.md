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
Register:     `POST http://localhost:8000/auth/register`  `{username, password}`
Login:        `POST http://localhost:8000/auth/login`     `{username, password}`
Logout:       `POST http://localhost:8000/auth/logout`    `Authorization: Bearer <token>`
New session:  `GET  http://localhost:8000/new-session`    `Authorization: Bearer <token>`
WebSocket:    `ws://localhost:8000/ws/{user_id}/{session_id}?token=<token>`

`new-session` and the WebSocket require a bearer token from `/auth/login` or `/auth/register`.
