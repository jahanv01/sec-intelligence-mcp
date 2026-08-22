"""Thin wrapper around the Gemini API for text generation."""

from functools import lru_cache

from google import genai
from google.genai.errors import ClientError
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from config import GEMINI_API_KEY, GEMINI_MODEL


@lru_cache(maxsize=1)
def _get_client() -> genai.Client:
    return genai.Client(api_key=GEMINI_API_KEY)


def _is_rate_limit_error(exc: BaseException) -> bool:
    return isinstance(exc, ClientError) and exc.code == 429


# The free-tier Gemini key this project uses hits its per-minute quota easily under any
# multi-call workload (e.g. the RAGAS eval harness's ~7 calls/question). The google-genai SDK
# itself has no built-in retry for this, unlike langchain's client -- without a retry here,
# any 429 crashes the whole caller instead of just slowing down.
@retry(
    retry=retry_if_exception(_is_rate_limit_error),
    wait=wait_exponential(multiplier=1, min=2, max=60),
    stop=stop_after_attempt(6),
    reraise=True,
)
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
