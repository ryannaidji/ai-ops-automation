from __future__ import annotations

from typing import get_args

from .llm import ChatLLM
from .models import Category, Classification, Sentiment, Urgency

SCHEMA = {
    "type": "object",
    "properties": {
        "category": {"type": "string", "enum": list(get_args(Category))},
        "urgency": {"type": "string", "enum": list(get_args(Urgency))},
        "sentiment": {"type": "string", "enum": list(get_args(Sentiment))},
    },
    "required": ["category", "urgency", "sentiment"],
}

SYSTEM = """You triage customer support tickets. Return JSON with:
- category: billing (charges, refunds, invoices), technical (bugs, errors, outages), account (login, password, profile, deletion), shipping (delivery, tracking), feedback (praise, suggestions), other.
- urgency: high (outage, security issue, fraud or money lost, legal deadline, many users blocked), medium (a single user is blocked or needs an answer soon), low (questions, suggestions, praise).
- sentiment: negative, neutral or positive."""


def classify(text: str, llm: ChatLLM) -> Classification:
    return Classification.model_validate(llm.chat_json(SYSTEM, text, SCHEMA))
