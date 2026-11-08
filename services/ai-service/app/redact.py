"""PII redaction: deterministic regex pass + optional small-LLM pass for names/addresses
that regexes miss. The LLM only *proposes* substrings; we replace only exact matches
found in the text, so the LLM can never inject or rewrite content."""
from __future__ import annotations

import logging
import re

from .llm import ChatLLM, LLMError
from .models import PiiSpan, RedactionResult

logger = logging.getLogger(__name__)

STREET = r"(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr|Court|Ct|Way|Place|Pl|Terrace|Ter)"

PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("EMAIL", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("CARD", re.compile(r"\b(?:\d[ -]?){12,18}\d\b")),
    ("SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("PHONE", re.compile(r"(?<![\w-])(?:\+?1[ .-]?)?(?:\(\d{3}\)\s?|\d{3}[ .-]?)\d{3}[ .-]?\d{4}\b")),
    (
        "ADDRESS",
        re.compile(
            rf"\b\d{{1,6}}\s+(?:[A-Z][A-Za-z]+\.?\s+){{1,4}}{STREET}\b\.?"
            r"(?:,?\s*(?:Apt|Suite|Unit|#)\s*\w+)?"
        ),
    ),
]


def luhn_ok(candidate: str) -> bool:
    nums = [int(c) for c in candidate if c.isdigit()]
    if not 13 <= len(nums) <= 19:
        return False
    total = 0
    for i, n in enumerate(reversed(nums)):
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def find_regex_spans(text: str) -> list[PiiSpan]:
    spans: list[PiiSpan] = []
    for kind, pat in PATTERNS:
        for m in pat.finditer(text):
            if kind == "CARD" and not luhn_ok(m.group()):
                continue
            spans.append(PiiSpan(type=kind, start=m.start(), end=m.end()))
    return spans


LLM_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": ["NAME", "ADDRESS"]},
                    "text": {"type": "string"},
                },
                "required": ["type", "text"],
            },
        }
    },
    "required": ["items"],
}

LLM_SYSTEM = (
    "You are a PII detector. Find person names (NAME) and street addresses (ADDRESS) in the TEXT "
    "the user gives you. Copy each one exactly as written. Ignore company/product names and "
    "placeholder tokens like [EMAIL]."
)


def llm_user_prompt(text: str) -> str:
    # Delimiting the ticket matters: without it, small models (qwen2.5:3b) answer the
    # ticket instead of extracting from it and return empty lists.
    return f'TEXT:\n"""\n{text}\n"""\nList the person names and street addresses found in TEXT.'


def find_llm_spans(text: str, llm: ChatLLM) -> list[PiiSpan]:
    try:
        out = llm.chat_json(LLM_SYSTEM, llm_user_prompt(text), LLM_SCHEMA)
    except LLMError as e:
        logger.warning("llm redaction pass skipped: %s", e)
        return []
    spans: list[PiiSpan] = []
    for item in out.get("items", []) or []:
        frag = str(item.get("text", "")).strip()
        kind = item.get("type", "NAME")
        if len(frag) < 3 or kind not in ("NAME", "ADDRESS") or "[" in frag:
            continue
        for m in re.finditer(re.escape(frag), text):
            spans.append(PiiSpan(type=kind, start=m.start(), end=m.end()))
    return spans


def merge_spans(spans: list[PiiSpan]) -> list[PiiSpan]:
    """Resolve overlaps: earliest start wins, longer span preferred on ties."""
    ordered = sorted(spans, key=lambda s: (s.start, -(s.end - s.start)))
    kept: list[PiiSpan] = []
    for s in ordered:
        if kept and s.start < kept[-1].end:
            continue
        kept.append(s)
    return kept


def redact(text: str, llm: ChatLLM | None = None) -> RedactionResult:
    spans = find_regex_spans(text)
    if llm is not None:
        spans += find_llm_spans(text, llm)
    spans = merge_spans(spans)
    out: list[str] = []
    cursor = 0
    counts: dict[str, int] = {}
    for s in spans:
        out.append(text[cursor : s.start])
        out.append(f"[{s.type}]")
        cursor = s.end
        counts[s.type] = counts.get(s.type, 0) + 1
    out.append(text[cursor:])
    return RedactionResult(redacted="".join(out), entities=spans, counts=counts)
