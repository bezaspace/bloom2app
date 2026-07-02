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
    add_biomarkers,
    add_doc_record,
    delete_daily_schedule,
    get_daily_logs,
    get_daily_schedule,
    get_profile,
    get_recent_daily_logs,
    get_user_by_token,
    init_db,
    list_biomarkers,
    list_biomarkers_by_name,
    list_docs,
    save_daily_log,
    save_daily_schedule,
    save_profile,
)
from app.dashboard.biomarkers import extract_biomarkers
from app.dashboard.generator import generate_daily_schedule
from app.dashboard.schemas import (
    DashboardToday,
    DailyLogRequest,
    WELLNESS_DOMAINS,
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

    # Second pass: extract structured numeric biomarker readings (for the
    # dashboard trend charts). Runs in parallel with nothing else but is
    # best-effort — failures here don't fail the upload.
    biomarker_count = 0
    try:
        readings = await extract_biomarkers(data, mime_type, safe_name)
        if readings:
            await add_biomarkers(user, readings)
            biomarker_count = len(readings)
    except Exception as e:  # noqa: BLE001
        logger.warning("Biomarker extraction failed for %s: %s", user, e)

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
        "biomarkers_extracted": biomarker_count,
    }


# ---------------------------------------------------------------------------
# Dashboard endpoints
# ---------------------------------------------------------------------------
def _today_iso() -> str:
    from datetime import date
    return date.today().isoformat()


@app.get("/dashboard/today")
async def dashboard_today(user: str = Depends(get_current_user)) -> dict:
    """Return everything the dashboard needs for today in one call:
    onboarding status, plan summary, the AI-generated daily schedule (generated
    on first request and cached), today's per-domain logs, and a biomarker
    count.
    """
    profile_data = await get_profile(user)
    onboarded = bool(profile_data and profile_data.get("onboarded"))
    if not onboarded:
        return DashboardToday(
            date=_today_iso(),
            onboarded=False,
            day_of_plan=0,
            phase="",
        ).model_dump()

    plan = profile_data.get("plan") or {}
    profile = profile_data.get("profile") or {}
    doc_summary = profile_data.get("doc_summary")
    onboarded_at = profile_data.get("onboarded_at")

    # Generate (or fetch cached) today's schedule.
    iso_date = _today_iso()
    schedule_dict = await get_daily_schedule(user, iso_date)
    if not schedule_dict:
        schedule = await generate_daily_schedule(
            profile=profile,
            plan=plan,
            doc_summary=doc_summary,
            onboarded_at=onboarded_at,
            target_date=iso_date,
        )
        schedule_dict = schedule.model_dump()
        await save_daily_schedule(user, iso_date, json.dumps(schedule_dict))

    # Fetch today's logs (keyed by domain).
    logs = await get_daily_logs(user, iso_date)

    # Biomarker count for the header badge.
    biomarkers = await list_biomarkers(user)

    # Current phase focus for the plan summary card.
    day_of_plan = schedule_dict.get("day_of_plan", 1)
    phase = schedule_dict.get("phase", "")
    phases = plan.get("phases", []) if plan else []
    phase_focus = ""
    if phases:
        idx = min(len(phases) - 1, (day_of_plan - 1) // 30)
        phase_focus = phases[idx].get("focus", "")

    return DashboardToday(
        date=iso_date,
        onboarded=True,
        day_of_plan=day_of_plan,
        phase=phase,
        plan_summary=plan.get("summary") if plan else None,
        plan_phase_focus=phase_focus or None,
        schedule=schedule_dict,
        logs=logs,
        biomarker_count=len(biomarkers),
    ).model_dump()


@app.post("/dashboard/schedule/regenerate")
async def dashboard_regenerate_schedule(
    user: str = Depends(get_current_user),
) -> dict:
    """Delete today's cached schedule and generate a fresh one."""
    profile_data = await get_profile(user)
    if not profile_data or not profile_data.get("onboarded"):
        return {"status": "error", "message": "Not onboarded."}

    iso_date = _today_iso()
    await delete_daily_schedule(user, iso_date)

    plan = profile_data.get("plan") or {}
    profile = profile_data.get("profile") or {}
    doc_summary = profile_data.get("doc_summary")
    onboarded_at = profile_data.get("onboarded_at")

    schedule = await generate_daily_schedule(
        profile=profile,
        plan=plan,
        doc_summary=doc_summary,
        onboarded_at=onboarded_at,
        target_date=iso_date,
    )
    schedule_dict = schedule.model_dump()
    await save_daily_schedule(user, iso_date, json.dumps(schedule_dict))
    return {"status": "success", "schedule": schedule_dict}


@app.post("/dashboard/log")
async def dashboard_log(
    body: DailyLogRequest,
    user: str = Depends(get_current_user),
) -> dict:
    """Upsert a per-domain daily log (replaces prior entries for that domain
    on that date)."""
    if body.domain not in WELLNESS_DOMAINS:
        return {
            "status": "error",
            "message": f"Invalid domain. Must be one of: {WELLNESS_DOMAINS}",
        }
    entries_json = json.dumps([e.model_dump() for e in body.entries])
    await save_daily_log(user, body.date, body.domain, entries_json)
    return {"status": "success"}


@app.get("/dashboard/logs/recent")
async def dashboard_recent_logs(
    domain: str,
    days: int = 7,
    user: str = Depends(get_current_user),
) -> dict:
    """Return the last `days` days of logs for a single domain (for 7-day
    bar charts). Days with no log row are omitted; the client fills gaps."""
    if domain not in WELLNESS_DOMAINS:
        return {
            "status": "error",
            "message": f"Invalid domain. Must be one of: {WELLNESS_DOMAINS}",
        }
    days = max(1, min(days, 90))
    rows = await get_recent_daily_logs(user, domain, days)
    return {"status": "success", "domain": domain, "days": days, "logs": rows}


@app.get("/dashboard/biomarkers")
async def dashboard_biomarkers(user: str = Depends(get_current_user)) -> dict:
    """Return all biomarker readings for the user, grouped by marker name.

    Each group contains the marker name, unit, reference/optimal ranges (from
    the most recent reading that has them), and the full history of readings
    (oldest first) for trend charts.
    """
    rows = await list_biomarkers(user)
    groups: dict[str, dict] = {}
    for r in rows:
        g = groups.setdefault(
            r["name"],
            {
                "name": r["name"],
                "unit": r["unit"],
                "ref_low": None,
                "ref_high": None,
                "optimal_low": None,
                "optimal_high": None,
                "readings": [],
            },
        )
        # Prefer the most recent non-null ranges.
        if g["ref_low"] is None and r["ref_low"] is not None:
            g["ref_low"] = r["ref_low"]
        if g["ref_high"] is None and r["ref_high"] is not None:
            g["ref_high"] = r["ref_high"]
        if g["optimal_low"] is None and r["optimal_low"] is not None:
            g["optimal_low"] = r["optimal_low"]
        if g["optimal_high"] is None and r["optimal_high"] is not None:
            g["optimal_high"] = r["optimal_high"]
        g["readings"].append(r)
    # Reverse each group's readings to oldest-first for charting.
    for g in groups.values():
        g["readings"].reverse()
    return {"status": "success", "groups": list(groups.values())}


@app.get("/dashboard/biomarkers/{name}")
async def dashboard_biomarker_detail(
    name: str,
    user: str = Depends(get_current_user),
) -> dict:
    """Return the full history for a single biomarker (oldest first)."""
    rows = await list_biomarkers_by_name(user, name)
    return {"status": "success", "name": name, "readings": rows}


@app.post("/dashboard/biomarkers/refresh-from-docs")
async def dashboard_refresh_biomarkers(
    user: str = Depends(get_current_user),
) -> dict:
    """Re-run biomarker extraction over all of the user's uploaded lab
    documents. Useful after the extraction prompt is improved, or if the
    initial extraction failed."""
    from pathlib import Path

    docs = await list_docs(user)
    user_dir = UPLOADS_DIR / user
    total = 0
    skipped = 0
    for doc in docs:
        # Find the file on disk (files are stored with a uuid prefix).
        matches = list(user_dir.glob(f"*_{doc['filename']}"))
        if not matches:
            skipped += 1
            continue
        file_path = matches[0]
        data = file_path.read_bytes()
        try:
            readings = await extract_biomarkers(
                data, doc["mime_type"], doc["filename"]
            )
            if readings:
                await add_biomarkers(user, readings)
                total += len(readings)
        except Exception as e:  # noqa: BLE001
            logger.warning("Re-extraction failed for %s: %s", doc["filename"], e)
    return {
        "status": "success",
        "extracted": total,
        "skipped": skipped,
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
