"""LLM hook, title, and hashtag generation from clip transcripts.

The plan's "hook engineering" stage (§4): the first ~2 seconds of a short get a
burned-in text hook ("he did NOT expect this..."), and every clip needs a
platform-ready title and hashtags. Claude generates all three from the clip
transcript in one structured-output call.

Requires the optional dependency: ``pip install 'clipengine[llm]'`` and an
``ANTHROPIC_API_KEY`` in the environment. Server-side refusal fallbacks are
enabled by default so a safety-classifier decline transparently retries on a
fallback model instead of failing the clip.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass

DEFAULT_MODEL = "claude-opus-5"

_SCHEMA = {
    "type": "object",
    "properties": {
        "hook": {
            "type": "string",
            "description": "On-screen text hook for the first 2 seconds, <=7 words, no quotes",
        },
        "title": {
            "type": "string",
            "description": "Video title, <=80 chars, punchy but faithful to the clip",
        },
        "hashtags": {
            "type": "array",
            "items": {"type": "string"},
            "description": "3-6 lowercase hashtags without the # prefix",
        },
    },
    "required": ["hook", "title", "hashtags"],
    "additionalProperties": False,
}

_SYSTEM = """You write packaging for short-form gaming clips (TikTok / YouTube Shorts).
Given a clip transcript, produce:
- hook: on-screen text for the first 2 seconds. <=7 words, high tension or humour,
  no spoilers of the punchline, no emoji, no surrounding quotes.
- title: <=80 characters. Punchy and curiosity-driving but faithful to what actually
  happens - never fabricate events that are not in the transcript.
- hashtags: 3-6 lowercase tags without '#', mixing broad (gaming, fyp) and specific
  (the game or streamer) reach.
Transcripts come from automatic speech recognition and may contain errors - infer the
moment's energy from context rather than trusting every word."""


@dataclass
class Suggestion:
    hook: str
    title: str
    hashtags: list[str]


def available() -> bool:
    """True when hook generation can run (API key present)."""
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def generate(
    transcript_text: str,
    streamer: str,
    client=None,
    model: str = DEFAULT_MODEL,
) -> Suggestion | None:
    """Generate hook/title/hashtags for one clip. Returns None when unavailable
    (empty transcript, refusal, or malformed output) - a clip without a
    suggestion is still a valid clip."""
    if not transcript_text.strip():
        return None
    if client is None:
        try:
            import anthropic
        except ImportError as e:
            raise RuntimeError(
                "anthropic SDK not installed - run: pip install 'clipengine[llm]'"
            ) from e
        client = anthropic.Anthropic()

    response = client.beta.messages.create(
        model=model,
        max_tokens=4000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        system=_SYSTEM,
        messages=[
            {
                "role": "user",
                "content": (
                    f"Streamer: {streamer}\n"
                    f"Clip transcript:\n{transcript_text.strip()}"
                ),
            }
        ],
        output_config={"format": {"type": "json_schema", "schema": _SCHEMA}},
    )
    if response.stop_reason == "refusal":
        return None
    text = next((b.text for b in response.content if b.type == "text"), "")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    hashtags = []
    for tag in data.get("hashtags", []):
        tag = tag.strip().lstrip("#").lower().replace(" ", "")
        if tag and tag not in hashtags:
            hashtags.append(tag)
    return Suggestion(
        hook=data["hook"].strip().strip('"'),
        title=data["title"].strip(),
        hashtags=hashtags,
    )
