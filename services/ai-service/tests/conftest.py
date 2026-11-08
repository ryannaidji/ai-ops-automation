"""Fakes so the whole suite runs without Ollama."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings  # noqa: E402
from app.main import Deps, create_app  # noqa: E402
from app.models import Answer, Source  # noqa: E402
from app.security import sign  # noqa: E402
from app.store import TicketStore  # noqa: E402

SECRET = "test-secret"


class FakeLLM:
    """Keyword rules standing in for the model; returns schema-shaped JSON."""

    def __init__(self, names: list[str] | None = None):
        self.names = names or []
        self.calls: list[str] = []

    def chat_json(self, system, user, schema):
        self.calls.append(user)
        if "items" in schema["properties"]:  # redaction pass
            return {"items": [{"type": "NAME", "text": n} for n in self.names if n in user]}
        t = user.lower()
        category = (
            "billing" if any(w in t for w in ("refund", "charge", "invoice"))
            else "account" if any(w in t for w in ("password", "login", "2fa"))
            else "technical" if any(w in t for w in ("error", "down", "outage"))
            else "other"
        )
        urgency = "high" if any(w in t for w in ("outage", "down", "fraud", "urgent")) else "low"
        sentiment = "negative" if any(w in t for w in ("angry", "terrible", "worst")) else "neutral"
        return {"category": category, "urgency": urgency, "sentiment": sentiment}


class FakeAnswerer:
    def answer(self, question, top_k=3):
        if "password" in question.lower():
            return Answer(answer="Use 'Forgot password'; the link is valid for 1 hour.",
                          sources=[Source(file="account.md", score=0.9, snippet="Password reset")])
        return Answer(answer="I don't know based on the knowledge base.", sources=[])


@pytest.fixture
def fake_llm():
    return FakeLLM(names=["Maria Lopez"])


@pytest.fixture
def client(fake_llm, monkeypatch):
    monkeypatch.setenv("WEBHOOK_SECRET", SECRET)
    deps = Deps(settings=Settings(), llm=fake_llm, answerer_factory=FakeAnswerer, store=TicketStore(":memory:"))
    return TestClient(create_app(deps))


def signed_headers(payload: dict, secret: str = SECRET, ts: int | None = None) -> tuple[bytes, dict]:
    body = json.dumps(payload).encode()
    t = str(ts if ts is not None else int(time.time()))
    return body, {"X-Timestamp": t, "X-Signature": sign(secret, t, body), "Content-Type": "application/json"}
