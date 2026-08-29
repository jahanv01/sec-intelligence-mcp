"""RAGAS judge setup: wraps this project's Gemini key for use as RAGAS's LLM/embeddings judge.

Lives in src/ (not evaluation/) so both evaluation/run_eval.py and production tools (e.g.
analyze_filing's background faithfulness scoring, Issue 8.2) can import it.

Pinned dependency note: see the ragas/langchain-community/langchain-google-genai comment in
pyproject.toml -- this combo is the newest one that actually imports and runs.
"""

from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from ragas.embeddings import LangchainEmbeddingsWrapper
from ragas.llms import LangchainLLMWrapper

from config import GEMINI_API_KEY, GEMINI_MODEL


def get_judge_llm() -> LangchainLLMWrapper:
    chat = ChatGoogleGenerativeAI(model=GEMINI_MODEL, google_api_key=GEMINI_API_KEY)
    return LangchainLLMWrapper(chat)


def get_judge_embeddings() -> LangchainEmbeddingsWrapper:
    embeddings = GoogleGenerativeAIEmbeddings(
        model="models/gemini-embedding-001", google_api_key=GEMINI_API_KEY
    )
    return LangchainEmbeddingsWrapper(embeddings)
