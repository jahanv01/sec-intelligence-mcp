"""RAGAS judge setup: wraps this project's Gemini key for use as RAGAS's LLM/embeddings judge.

Pinned dependency note: see the ragas/langchain-community/langchain-google-genai comment in
pyproject.toml -- this combo is the newest one that actually imports and runs.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from ragas.embeddings import LangchainEmbeddingsWrapper
from ragas.llms import LangchainLLMWrapper

from config import GEMINI_API_KEY, GEMINI_MODEL  # noqa: E402


def get_judge_llm() -> LangchainLLMWrapper:
    chat = ChatGoogleGenerativeAI(model=GEMINI_MODEL, google_api_key=GEMINI_API_KEY)
    return LangchainLLMWrapper(chat)


def get_judge_embeddings() -> LangchainEmbeddingsWrapper:
    embeddings = GoogleGenerativeAIEmbeddings(
        model="models/gemini-embedding-001", google_api_key=GEMINI_API_KEY
    )
    return LangchainEmbeddingsWrapper(embeddings)
