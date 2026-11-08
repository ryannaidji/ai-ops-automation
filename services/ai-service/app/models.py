from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Category = Literal["billing", "technical", "account", "shipping", "feedback", "other"]
Urgency = Literal["low", "medium", "high"]
Sentiment = Literal["negative", "neutral", "positive"]


class TextIn(BaseModel):
    text: str = Field(min_length=1, max_length=20_000)


class Classification(BaseModel):
    category: Category
    urgency: Urgency
    sentiment: Sentiment


class PiiSpan(BaseModel):
    type: str
    start: int
    end: int


class RedactionResult(BaseModel):
    redacted: str
    entities: list[PiiSpan]
    counts: dict[str, int]


class AnswerIn(BaseModel):
    question: str = Field(min_length=1, max_length=5_000)
    top_k: int = Field(default=3, ge=1, le=10)


class Source(BaseModel):
    file: str
    score: float | None = None
    snippet: str


class Answer(BaseModel):
    answer: str
    sources: list[Source]


class TicketEvent(BaseModel):
    ticket_id: str = Field(min_length=1, max_length=100)
    subject: str = Field(default="", max_length=500)
    body: str = Field(min_length=1, max_length=20_000)
    channel: Literal["email", "chat", "form", "api"] = "api"


class RoutingDecision(BaseModel):
    ticket_id: str
    route: Literal["escalate", "queue", "auto_reply"]
    reason: str
    classification: Classification
    redacted_text: str
    pii_counts: dict[str, int]
    suggested_reply: str | None
    sources: list[Source]
    request_id: str


class TicketRecord(RoutingDecision):
    created_at: str
