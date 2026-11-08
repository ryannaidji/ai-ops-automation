"""Pure routing logic (no I/O, easy to unit test)."""
from __future__ import annotations

from .models import Classification

AUTO_REPLY_CATEGORIES = {"account", "shipping", "billing", "technical"}


def is_no_answer(answer: str | None) -> bool:
    return not answer or "i don't know" in answer.lower() or "i do not know" in answer.lower()


def decide(c: Classification, answer: str | None) -> tuple[str, str]:
    if c.urgency == "high":
        return "escalate", "urgency=high"
    if c.sentiment == "negative" and c.urgency == "medium":
        return "escalate", "negative sentiment with medium urgency"
    if not is_no_answer(answer) and c.category in AUTO_REPLY_CATEGORIES:
        return "auto_reply", f"knowledge-base answer found for {c.category}"
    return "queue", "no confident automated answer"
