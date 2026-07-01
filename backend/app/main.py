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
from fastapi import (
    Depends,
    FastAPI,
    File,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from google.adk.agents.live_request_queue import LiveRequestQueue
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

# Load environment variables from .env BEFORE importing the agent
load_dotenv(Path(__file__).parent.parent / ".env")

# pylint: disable=wrong-import-position
from app.auth import get_current_user
from app.auth import router as auth_router
from app.database import (
    add_doc_record,
    get_profile,
    get_user_by_token,
    init_db,
    list_docs,
    save_profile,
)
from app.document_processor import SUPPORTED_MIME_TYPES, process_document
from app.voice_agent.agent import agent  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("bloom2.backend")

APP_NAME = "bloom2"

# Directory for uploaded health documents (stored per user).
UPLOADS_DIR = Path(__file__).parent.parent / "uploads"

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

app.include_router(auth_router)


@app.on_event("startup")
async def startup() -> None:
    await init_db()


@app.get("/health")
async def health() -> dict:
    """Simple health check."""
    return {"status": "ok", "model": agent.model}


@app.get("/new-session")
async def new_session(user: str = Depends(get_current_user)) -> dict:
    """Generate a fresh user_id / session_id pair for a new conversation."""
    return {
        "user_id": f"user-{uuid.uuid4().hex[:8]}",
        "session_id": f"session-{uuid.uuid4().hex[:12]}",
    }


@app.get("/onboarding-status")
async def onboarding_status(user: str = Depends(get_current_user)) -> dict:
    """Return the user's onboarding status, profile, plan, and uploaded docs."""
    profile_data = await get_profile(user)
    docs = await list_docs(user)
    if not profile_data:
        return {"onboarded": False, "profile": None, "plan": None, "documents": docs}
    return {
        "onboarded": profile_data["onboarded"],
        "profile": profile_data["profile"],
        "plan": profile_data["plan"],
        "doc_summary": profile_data["doc_summary"],
        "documents": docs,
    }


@app.post("/upload-doc")
async def upload_doc(
    user: str = Depends(get_current_user),
    file: UploadFile = File(...),
) -> dict:
    """Upload a health document (PDF or image), process it with Gemini Flash-Lite,
    and store the structured summary on the user's profile.

    The extracted summary is merged into the user's profile so the live voice
    agent can pick it up via the get_document_summary tool during onboarding.
    """
    mime_type = file.content_type or ""
    if mime_type not in SUPPORTED_MIME_TYPES:
        return {
            "status": "error",
            "message": f"Unsupported file type: {mime_type}. Supported: {sorted(SUPPORTED_MIME_TYPES)}",
        }

    data = await file.read()
    if not data:
        return {"status": "error", "message": "Empty file."}

    # Save the file to disk for record-keeping.
    user_dir = UPLOADS_DIR / user
    user_dir.mkdir(parents=True, exist_ok=True)
    safe_name = Path(file.filename or "upload").name
    file_path = user_dir / f"{uuid.uuid4().hex[:8]}_{safe_name}"
    file_path.write_bytes(data)

    # Record metadata in the database.
    await add_doc_record(user, safe_name, mime_type)

    # Process with Gemini Flash-Lite for structured extraction.
    try:
        summary = await process_document(data, mime_type)
    except Exception as e:  # noqa: BLE001
        logger.error("Document processing failed for %s: %s", user, e, exc_info=True)
        return {"status": "error", "message": f"Document processing failed: {e}"}

    # Merge the summary into the user's profile (create a stub if none exists yet
    # — onboarding may not be finalized yet, but we store the doc_summary so the
    # agent can read it when finalizing).
    existing = await get_profile(user)
    profile_json = json.dumps(existing["profile"]) if existing and existing.get("profile") else "{}"
    plan_json = json.dumps(existing["plan"]) if existing and existing.get("plan") else "{}"
    doc_summary_json = json.dumps(summary)
    onboarded = existing["onboarded"] if existing else False

    await save_profile(
        username=user,
        profile_json=profile_json,
        plan_json=plan_json,
        doc_summary_json=doc_summary_json,
        onboarded=onboarded,
    )

    logger.info("Document processed for %s: %s (%d bytes)", user, safe_name, len(data))
    return {
        "status": "success",
        "filename": safe_name,
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------
@app.websocket("/ws/{user_id}/{session_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    user_id: str,
    session_id: str,
    token: str | None = None,
) -> None:
    """Bidirectional streaming endpoint backed by ADK run_live()."""
    logger.info("WebSocket connect: user_id=%s session_id=%s", user_id, session_id)

    if not token or not await get_user_by_token(token):
        await websocket.close(code=1008)
        logger.warning("WebSocket rejected: missing or invalid token")
        return

    # Resolve the actual username from the token so onboarding tools can read it
    # from the session state.
    username = await get_user_by_token(token)
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
        session = await session_service.create_session(
            app_name=APP_NAME,
            user_id=user_id,
            session_id=session_id,
            state={"username": username},
        )
    else:
        # Ensure the username is present in the existing session's state.
        session.state["username"] = username

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
