"""Health document processor using Gemini 3.1 Flash-Lite.

Uploads (PDF / PNG / JPEG / WEBP) are sent inline to ``gemini-3.1-flash-lite``
with a Pydantic structured-output schema so we get a consistent, JSON-serializable
summary back. This summary is stored on the user's profile and read by the live
voice agent via the ``get_document_summary`` tool when building the 90-day plan.

This runs OUTSIDE the Gemini Live API session — the Live API does not process
uploaded files mid-session. We process the upload via a regular
``generate_content`` call, persist the result, and the live agent picks it up.
"""

import logging
import os
from typing import Optional

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

logger = logging.getLogger("bloom2.doc_processor")

# Stable Flash-Lite model (May 2026). Low cost / latency, supports PDF + image
# inputs and structured output. Override via env if a newer model is preferred.
DOC_MODEL = os.getenv("DOC_MODEL", "gemini-3.1-flash-lite")

# MIME types we accept for upload.
SUPPORTED_MIME_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/webp",
}


class DocumentSummary(BaseModel):
    """Structured summary extracted from a health document."""

    conditions: list[str] = Field(
        default_factory=list,
        description="Diagnosed medical conditions or diseases mentioned (empty list if none).",
    )
    medications: list[str] = Field(
        default_factory=list,
        description="Medications, supplements, or prescriptions mentioned (empty list if none).",
    )
    allergies: list[str] = Field(
        default_factory=list,
        description="Allergies or sensitivities mentioned (empty list if none).",
    )
    recent_labs: list[str] = Field(
        default_factory=list,
        description="Recent lab results, vitals, or measurements with values if available (empty list if none).",
    )
    lifestyle_notes: str = Field(
        default="",
        description="Lifestyle-related notes: diet, exercise, sleep, stress, smoking, alcohol.",
    )
    red_flags: list[str] = Field(
        default_factory=list,
        description="Anything that should be flagged for clinician follow-up (empty list if none).",
    )
    free_text_summary: str = Field(
        default="",
        description="A 2-3 sentence plain-language summary of what this document contains.",
    )


def _client() -> genai.Client:
    """Build a google-genai client from the GOOGLE_API_KEY env var."""
    return genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))


async def process_document(data: bytes, mime_type: str) -> dict:
    """Send a single health document to Flash-Lite and return a structured summary.

    Args:
        data: Raw file bytes (PDF or image).
        mime_type: One of SUPPORTED_MIME_TYPES.

    Returns:
        A dict matching :class:`DocumentSummary` (JSON-serializable).
    """
    if mime_type not in SUPPORTED_MIME_TYPES:
        raise ValueError(f"Unsupported mime type: {mime_type}")

    client = _client()
    part = types.Part(inline_data=types.Blob(mime_type=mime_type, data=data))
    prompt = (
        "You are reviewing a health document (lab report, prescription, discharge "
        "summary, or similar) provided by a user of an experimental wellness app. "
        "Extract the relevant information into the structured schema. Only include "
        "information explicitly present in the document — do not infer or fabricate. "
        "If a field is not applicable, leave it empty. This is for experimentation "
        "purposes only and is not a medical diagnosis."
    )

    response = await client.aio.models.generate_content(
        model=DOC_MODEL,
        contents=types.Content(parts=[part, types.Part(text=prompt)]),
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=DocumentSummary,
            temperature=0.1,
        ),
    )

    # With response_schema set, response.parsed gives a validated DocumentSummary.
    parsed: Optional[DocumentSummary] = response.parsed
    if parsed is not None:
        return parsed.model_dump()

    # Fallback: parse the text manually if parsed is unavailable.
    import json

    text = response.text or "{}"
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        logger.warning("Could not parse document summary JSON; returning empty.")
        return DocumentSummary().model_dump()
