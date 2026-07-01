"""FastAPI application: WebSocket bridge between a mobile client and ADK Live API.

Architecture:
    Mobile app (WebSocket)  <-->  FastAPI  <-->  ADK Runner.run_live()  <-->  Gemini Live API

The client streams 16kHz PCM audio (binary frames) and text (JSON frames) upstream.
The server forwards them to a LiveRequestQueue. ADK's run_live() consumes the queue,
talks to the Gemini Live API, and yields Events (audio chunks + transcripts) which
the server streams back down to the client as JSON.
"""

import asyncio
import json
import logging
import os
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from google.adk.agents.live_request_queue import LiveRequestQueue
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

# Load environment variables from .env BEFORE importing the agent
load_dotenv(Path(__file__).parent.parent / ".env")

# pylint: disable=wrong-import-position
from app.voice_agent.agent import agent  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("bloom2.backend")

APP_NAME = "bloom2"

# ---------------------------------------------------------------------------
# Application initialization (once at startup)
# ---------------------------------------------------------------------------
app = FastAPI(title="Bloom2 Voice Assistant Backend")

# Allow the Expo dev client / web browser to connect during development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

session_service = InMemorySessionService()
runner = Runner(
    app_name=APP_NAME,
    agent=agent,
    session_service=session_service,
)


@app.get("/health")
async def health() -> dict:
    """Simple health check."""
    return {"status": "ok", "model": agent.model}


@app.get("/new-session")
async def new_session() -> dict:
    """Generate a fresh user_id / session_id pair for a new conversation."""
    return {
        "user_id": f"user-{uuid.uuid4().hex[:8]}",
        "session_id": f"session-{uuid.uuid4().hex[:12]}",
    }


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------
@app.websocket("/ws/{user_id}/{session_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    user_id: str,
    session_id: str,
) -> None:
    """Bidirectional streaming endpoint backed by ADK run_live()."""
    logger.info("WebSocket connect: user_id=%s session_id=%s", user_id, session_id)
    await websocket.accept()

    # We use AUDIO response modality so the model speaks back. The
    # gemini-3.1-flash-live-preview model is a native-audio live model, so we
    # also enable input/output transcription to get text transcripts of the
    # conversation for the UI.
    run_config = RunConfig(
        streaming_mode=StreamingMode.BIDI,
        response_modalities=["AUDIO"],
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
        session_resumption=types.SessionResumptionConfig(),
    )

    # Get or create the ADK session for this conversation.
    session = await session_service.get_session(
        app_name=APP_NAME, user_id=user_id, session_id=session_id
    )
    if not session:
        await session_service.create_session(
            app_name=APP_NAME, user_id=user_id, session_id=session_id
        )

    live_request_queue = LiveRequestQueue()

    async def upstream_task() -> None:
        """Read frames from the client and push them into the LiveRequestQueue."""
        logger.debug("upstream_task started")
        while True:
            message = await websocket.receive()

            # Binary frame = raw 16kHz PCM audio from the microphone.
            if "bytes" in message and message["bytes"] is not None:
                audio_blob = types.Blob(
                    mime_type="audio/pcm;rate=16000", data=message["bytes"]
                )
                live_request_queue.send_realtime(audio_blob)

            # Text frame = JSON control message (e.g. typed text).
            elif "text" in message and message["text"] is not None:
                try:
                    json_message = json.loads(message["text"])
                except json.JSONDecodeError:
                    logger.warning("Unparseable text frame: %s", message["text"][:100])
                    continue

                if json_message.get("type") == "text":
                    content = types.Content(
                        parts=[types.Part(text=json_message["text"])]
                    )
                    live_request_queue.send_content(content)

    async def downstream_task() -> None:
        """Stream ADK Events (audio + transcripts) back to the client as JSON."""
        logger.debug("downstream_task started")
        async for event in runner.run_live(
            user_id=user_id,
            session_id=session_id,
            live_request_queue=live_request_queue,
            run_config=run_config,
        ):
            event_json = event.model_dump_json(exclude_none=True, by_alias=True)
            await websocket.send_text(event_json)
        logger.debug("run_live() generator completed")

    try:
        await asyncio.gather(upstream_task(), downstream_task())
    except WebSocketDisconnect:
        logger.info("Client disconnected: %s/%s", user_id, session_id)
    except Exception as e:  # noqa: BLE001
        logger.error("Streaming error: %s", e, exc_info=True)
    finally:
        live_request_queue.close()
        logger.info("Session closed: %s/%s", user_id, session_id)


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("app.main:app", host=host, port=port, reload=True)
