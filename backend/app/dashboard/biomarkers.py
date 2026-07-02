"""Structured biomarker extraction from uploaded lab documents.

This is a second pass over the same document bytes that ``document_processor``
already handles. The first pass extracts a free-text clinical summary for the
voice agent; this pass extracts *numeric* biomarker readings (HbA1c, LDL,
vitamin D, TSH, etc.) with their reference and optimal ranges so the dashboard
can plot trend charts with shaded range bands.

Both passes use ``gemini-3.1-flash-lite`` with Pydantic structured output —
the same pattern as ``app/document_processor.py``.
"""

import logging
import os
from typing import Optional

from google import genai
from google.genai import types

from app.dashboard.schemas import BiomarkerExtraction

logger = logging.getLogger("bloom2.biomarkers")

# Same Flash-Lite model as the document processor. Override via env if needed.
BIOMARKER_MODEL = os.getenv("DOC_MODEL", "gemini-3.1-flash-lite")


def _client() -> genai.Client:
    return genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))


async def extract_biomarkers(
    data: bytes, mime_type: str, source_doc: str
) -> list[dict]:
    """Extract structured biomarker readings from a lab document.

    Args:
        data: Raw file bytes (PDF or image).
        mime_type: One of the supported upload MIME types.
        source_doc: Filename of the source document (recorded on each reading).

    Returns:
        A list of dicts matching :class:`BiomarkerReading` (JSON-serializable),
        ready to be inserted via ``database.add_biomarkers``. Empty list if no
        biomarkers could be extracted (e.g. the document is a prescription with
        no lab values).
    """
    client = _client()
    part = types.Part(inline_data=types.Blob(mime_type=mime_type, data=data))
    prompt = (
        "You are reviewing a health document (lab report, blood panel, or "
        "similar) provided by a user of an experimental wellness app. Extract "
        "every numeric biomarker reading you can find in the document into the "
        "structured schema. For each reading, capture: the standardized marker "
        "name (use the canonical clinical name, e.g. 'HbA1c', 'LDL Cholesterol', "
        "'Vitamin D (25-OH)', 'TSH', 'Fasting Glucose'), the numeric value, the "
        "unit, the reference range bounds printed on the report (if any), and "
        "the date the sample was collected (if present). "
        "Only include values explicitly present in the document — do not infer, "
        "calculate, or fabricate. If the document is not a lab report (e.g. a "
        "prescription or discharge summary with no lab values), return an empty "
        "readings list. This is for experimentation purposes only and is not a "
        "medical diagnosis."
    )

    try:
        response = await client.aio.models.generate_content(
            model=BIOMARKER_MODEL,
            contents=types.Content(parts=[part, types.Part(text=prompt)]),
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=BiomarkerExtraction,
                temperature=0.1,
            ),
        )
    except Exception as e:  # noqa: BLE001
        logger.error("Biomarker extraction failed: %s", e, exc_info=True)
        return []

    parsed: Optional[BiomarkerExtraction] = response.parsed
    if parsed is not None:
        readings = parsed.model_dump()["readings"]
    else:
        # Fallback: parse text manually.
        import json

        text = response.text or "{}"
        try:
            data_dict = json.loads(text)
            readings = data_dict.get("readings", [])
        except json.JSONDecodeError:
            logger.warning("Could not parse biomarker JSON; returning empty.")
            return []

    # Stamp the source_doc onto each reading (the model doesn't know it).
    for r in readings:
        if not r.get("source_doc"):
            r["source_doc"] = source_doc

    logger.info(
        "Extracted %d biomarker readings from %s", len(readings), source_doc
    )
    return readings
