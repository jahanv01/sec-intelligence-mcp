"""Tests for src/config.py fail-fast env var loading."""

import importlib
import sys

import pytest

REQUIRED_VARS = ["GEMINI_API_KEY", "QDRANT_URL", "LANGFUSE_SECRET_KEY", "LANGFUSE_PUBLIC_KEY"]


def _reload_config():
    sys.modules.pop("config", None)
    return importlib.import_module("config")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for var in [*REQUIRED_VARS, "QDRANT_API_KEY"]:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: None)


@pytest.mark.parametrize("missing_var", REQUIRED_VARS)
def test_raises_when_required_var_missing(monkeypatch, missing_var):
    for var in REQUIRED_VARS:
        if var != missing_var:
            monkeypatch.setenv(var, "dummy")

    with pytest.raises(RuntimeError, match=missing_var):
        _reload_config()


def test_loads_successfully_when_all_required_vars_present(monkeypatch):
    for var in REQUIRED_VARS:
        monkeypatch.setenv(var, "dummy")

    config = _reload_config()

    assert config.GEMINI_API_KEY == "dummy"
    assert config.QDRANT_API_KEY is None


@pytest.mark.parametrize(
    ("var", "attr", "default"),
    [
        ("EMBEDDING_MODEL", "EMBEDDING_MODEL", "intfloat/e5-base-v2"),
        ("GEMINI_MODEL", "GEMINI_MODEL", "gemini-flash-lite-latest"),
        ("SEC_EDGAR_USER_AGENT", "SEC_EDGAR_USER_AGENT", "sec-intelligence-mcp dev@example.com"),
    ],
)
def test_blank_optional_var_falls_back_to_default(monkeypatch, var, attr, default):
    """Regression test: a real deployment shipped `.env` with these left blank (not unset,
    per .env.example's documented pattern) and got "" instead of the default -- os.getenv's
    `default` argument only applies when the var is entirely absent, not when it's present
    but empty. Caught live on an Oracle Cloud deploy as an opaque crash three layers deep
    inside SentenceTransformer("") -- not an obviously env-related error at the failure site.
    """
    for required in REQUIRED_VARS:
        monkeypatch.setenv(required, "dummy")
    monkeypatch.setenv(var, "")

    config = _reload_config()

    assert getattr(config, attr) == default
