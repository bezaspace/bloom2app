"""Voice assistant agent powered by ADK + Gemini Live API."""

import os

from google.adk.agents import Agent

# The Gemini Live API model. gemini-3.1-flash-live-preview is the recommended
# native-audio live model (low-latency, real-time dialogue with audio output).
# Override via the AGENT_MODEL env var if needed.
DEFAULT_MODEL = "gemini-3.1-flash-live-preview"

agent = Agent(
    name="bloom2_voice_assistant",
    model=os.getenv("AGENT_MODEL", DEFAULT_MODEL),
    description=(
        "A friendly, conversational voice assistant that talks with the user "
        "naturally, like a friend."
    ),
    instruction=(
        "You are Bloom, a warm and friendly voice companion. You have natural, "
        "flowing back-and-forth conversations with the user, just like talking to "
        "a close friend. Keep your responses concise and conversational — speak in "
        "short, natural sentences rather than long monologues. Be curious, "
        "attentive, and empathetic. Ask follow-up questions to keep the "
        "conversation going. Avoid lists, markdown, or overly formal language "
        "since your responses are spoken aloud."
    ),
)
