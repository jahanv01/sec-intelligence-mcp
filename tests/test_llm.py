"""Tests for llm.py: Gemini wrapper retry behavior and JSON-fence stripping."""

from types import SimpleNamespace

import pytest
from google.genai.errors import ClientError

import llm


def _rate_limit_error() -> ClientError:
    return ClientError(429, {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED"}})


def _bad_request_error() -> ClientError:
    return ClientError(400, {"error": {"code": 400, "status": "INVALID_ARGUMENT"}})


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    # generate() is decorated at import time, so patch tenacity's sleep instead of re-wrapping.
    monkeypatch.setattr("tenacity.nap.time.sleep", lambda seconds: None)


def test_generate_retries_on_rate_limit_then_succeeds(monkeypatch):
    calls = {"count": 0}

    def fake_generate_content(model, contents):
        calls["count"] += 1
        if calls["count"] < 3:
            raise _rate_limit_error()
        return SimpleNamespace(text="the answer")

    fake_client = SimpleNamespace(models=SimpleNamespace(generate_content=fake_generate_content))
    monkeypatch.setattr(llm, "_get_client", lambda: fake_client)

    result = llm.generate("some prompt")

    assert result == "the answer"
    assert calls["count"] == 3


def test_generate_does_not_retry_on_non_rate_limit_error(monkeypatch):
    calls = {"count": 0}

    def fake_generate_content(model, contents):
        calls["count"] += 1
        raise _bad_request_error()

    fake_client = SimpleNamespace(models=SimpleNamespace(generate_content=fake_generate_content))
    monkeypatch.setattr(llm, "_get_client", lambda: fake_client)

    with pytest.raises(ClientError):
        llm.generate("some prompt")

    assert calls["count"] == 1


def test_generate_gives_up_after_max_attempts(monkeypatch):
    calls = {"count": 0}

    def fake_generate_content(model, contents):
        calls["count"] += 1
        raise _rate_limit_error()

    fake_client = SimpleNamespace(models=SimpleNamespace(generate_content=fake_generate_content))
    monkeypatch.setattr(llm, "_get_client", lambda: fake_client)

    with pytest.raises(ClientError):
        llm.generate("some prompt")

    assert calls["count"] == 6


def test_strip_json_fences_removes_markdown_fence():
    assert llm.strip_json_fences('```json\n{"a": 1}\n```') == '{"a": 1}'


def test_strip_json_fences_passes_through_plain_text():
    assert llm.strip_json_fences('{"a": 1}') == '{"a": 1}'
