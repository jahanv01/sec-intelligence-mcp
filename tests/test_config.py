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
