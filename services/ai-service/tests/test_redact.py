import pytest

from app.llm import LLMError
from app.redact import luhn_ok, redact


@pytest.mark.parametrize(
    "text,kind",
    [
        ("mail me at jane.doe+test@example.co.uk please", "EMAIL"),
        ("call (305) 555-0142 tonight", "PHONE"),
        ("call 305-555-0142 tonight", "PHONE"),
        ("call +1 305 555 0142 tonight", "PHONE"),
        ("card 4111 1111 1111 1111 was charged", "CARD"),
        ("card 4111-1111-1111-1111 was charged", "CARD"),
        ("ship to 1200 Brickell Bay Drive, Apt 4B today", "ADDRESS"),
        ("I live at 42 Ocean Ave now", "ADDRESS"),
        ("ssn 123-45-6789", "SSN"),
    ],
)
def test_regex_detects(text, kind):
    r = redact(text)
    assert f"[{kind}]" in r.redacted
    assert r.counts.get(kind) == 1


def test_non_luhn_number_not_card():
    assert not luhn_ok("1234 5678 9012 3456")
    r = redact("order number 1234 5678 9012 3456")
    assert "CARD" not in r.counts


def test_no_pii_unchanged():
    text = "The app crashes when I open settings on version 4.2."
    assert redact(text).redacted == text


def test_multiple_and_offsets():
    text = "Email a@b.io or call 305-555-0142."
    r = redact(text)
    assert r.redacted == "Email [EMAIL] or call [PHONE]."
    assert [text[s.start:s.end] for s in r.entities] == ["a@b.io", "305-555-0142"]


def test_llm_pass_adds_names_only_if_present(fake_llm):
    r = redact("Hi, this is Maria Lopez, my login fails.", fake_llm)
    assert r.redacted == "Hi, this is [NAME], my login fails."


class HallucinatingLLM:
    def chat_json(self, *a):
        return {"items": [{"type": "NAME", "text": "Bob Smith"}, {"type": "NAME", "text": "[EMAIL]"}]}


def test_llm_cannot_invent_or_rewrite():
    r = redact("contact x@y.com", HallucinatingLLM())
    assert r.redacted == "contact [EMAIL]"


class BrokenLLM:
    def chat_json(self, *a):
        raise LLMError("down")


def test_llm_failure_falls_back_to_regex():
    assert redact("x@y.com", BrokenLLM()).redacted == "[EMAIL]"
