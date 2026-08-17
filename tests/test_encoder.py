"""Tests for embeddings/encoder.py: E5 query/passage prefixing.

Uses a fake SentenceTransformer (no real model download) so this suite stays fast; the real
model is exercised separately by scripts/test_encoder.py.
"""

import numpy as np
import pytest

from embeddings import encoder


class _FakeModel:
    def __init__(self):
        self.calls: list[list[str]] = []

    def encode(self, texts, convert_to_numpy=True, show_progress_bar=False):
        self.calls.append(list(texts))
        return np.zeros((len(texts), 768), dtype=np.float32)


@pytest.fixture(autouse=True)
def _fake_model(monkeypatch):
    model = _FakeModel()
    monkeypatch.setattr(encoder, "_model", model)
    return model


def test_encode_returns_correct_shape(_fake_model):
    result = encoder.encode(["passage: Apple reported revenue of $385B"])
    assert result.shape == (1, 768)


def test_encode_does_not_add_prefix(_fake_model):
    encoder.encode(["raw text, no prefix added by encode() itself"])
    assert _fake_model.calls[-1] == ["raw text, no prefix added by encode() itself"]


def test_encode_query_adds_query_prefix(_fake_model):
    encoder.encode_query("data center revenue growth")
    assert _fake_model.calls[-1] == ["query: data center revenue growth"]


def test_encode_query_returns_1d_vector(_fake_model):
    result = encoder.encode_query("revenue growth")
    assert result.shape == (768,)


def test_encode_passages_adds_passage_prefix(_fake_model):
    encoder.encode_passages(["Apple reported revenue of $385B", "iPhone sales grew 5%"])
    assert _fake_model.calls[-1] == [
        "passage: Apple reported revenue of $385B",
        "passage: iPhone sales grew 5%",
    ]
