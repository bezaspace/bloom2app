"""Dashboard package: AI-generated daily schedule, biomarker extraction, and
per-domain daily logging for the Bloom2 wellness dashboard.

Public modules:
    schemas     — Pydantic models for schedule, targets, biomarkers, logs.
    generator   — Gemini Flash-Lite daily schedule generation (cached per day).
    biomarkers  — Structured biomarker extraction from uploaded lab documents.
"""
