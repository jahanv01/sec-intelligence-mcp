"""Environment configuration. Fails fast at import time if required keys are missing."""

import os

from dotenv import load_dotenv

load_dotenv()

REQUIRED_VARS = [
    "GEMINI_API_KEY",
    "QDRANT_URL",
    "LANGFUSE_SECRET_KEY",
    "LANGFUSE_PUBLIC_KEY",
]

_missing = [name for name in REQUIRED_VARS if not os.getenv(name)]
if _missing:
    raise RuntimeError(
        "Missing required environment variable(s): "
        f"{', '.join(_missing)}. Copy .env.example to .env and fill in the values."
    )

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
QDRANT_URL = os.environ["QDRANT_URL"]
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")  # optional for local Qdrant
LANGFUSE_SECRET_KEY = os.environ["LANGFUSE_SECRET_KEY"]
LANGFUSE_PUBLIC_KEY = os.environ["LANGFUSE_PUBLIC_KEY"]
