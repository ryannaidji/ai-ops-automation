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

SYSTEM_V1 = """You triage customer support tickets. Return JSON with:
- category: billing (charges, refunds, invoices), technical (bugs, errors, outages), account (login, password, profile, deletion), shipping (delivery, tracking), feedback (praise, suggestions), other.
- urgency: high (outage, security issue, fraud or money lost, legal deadline, many users blocked), medium (a single user is blocked or needs an answer soon), low (questions, suggestions, praise).
- sentiment: negative, neutral or positive."""

SYSTEM_V2 = """You triage customer support tickets. Return JSON with category, urgency and sentiment.

category: billing (charges, refunds, invoices), technical (bugs, errors, outages), account (login, password,
profile, deletion), shipping (delivery, tracking), feedback (praise, suggestions), other.

urgency - decide with these rules, in order. When unsure, choose the LOWER level.
- high ONLY IF at least one is explicitly stated: a service outage or many users affected; a security
  incident or suspected fraud/account takeover; a legal or contractual deadline. One customer's problem is NOT high,
  even if it involves money or a failed login.
- medium: ONE customer is blocked from doing something or has a concrete problem to fix (a wrong charge, a failed
  upload, a missing package, cannot log in).
- low: a question about how something works, policy or timing questions, suggestions, praise, thanks.
Contact details (email, phone) in the ticket never change urgency.

sentiment: negative, neutral or positive.

Examples (format only; not from the evaluation set):
"Our whole team gets 503 errors on every page since 9am." -> technical, high, negative
"The export button does nothing when I click it." -> technical, medium, negative
"Is there a student discount on the annual plan?" -> billing, low, neutral
"Love the new calendar view, thanks!" -> feedback, low, positive"""

SYSTEM = SYSTEM_V2


PROMPTS = {"v1": SYSTEM_V1, "v2": SYSTEM_V2}


def classify(text: str, llm: ChatLLM, prompt: str | None = None) -> Classification:
    import os
    system = PROMPTS[prompt or os.getenv("CLASSIFY_PROMPT", "v2")]
    return Classification.model_validate(llm.chat_json(system, text, SCHEMA))
