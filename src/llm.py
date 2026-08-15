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
