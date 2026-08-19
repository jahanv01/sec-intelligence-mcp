"""Thin wrapper around the Gemini API for text generation."""

from functools import lru_cache

from google import genai

from config import GEMINI_API_KEY, GEMINI_MODEL


@lru_cache(maxsize=1)
def _get_client() -> genai.Client:
    return genai.Client(api_key=GEMINI_API_KEY)


def generate(prompt: str) -> str:
    response = _get_client().models.generate_content(model=GEMINI_MODEL, contents=prompt)
    return response.text


def strip_json_fences(text: str) -> str:
    """Strips a ```json ... ``` (or bare ```...```) markdown fence some LLMs wrap JSON in."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        text = text.rsplit("```", 1)[0].strip()
        if text.lower().startswith("json"):
            text = text[4:].strip()
    return text
