"""Deterministically generate 40 labelled synthetic tickets -> evals/tickets.jsonl.

All names, emails, phones, card numbers (Luhn-valid test numbers) and addresses are fake.
Labels: category, urgency, contains_pii, pii (exact planted strings), and for KB questions
`kb_file` + `kb_fact` (a phrase from docs/ the answer should contain).
"""
from __future__ import annotations

import json
import random
from pathlib import Path

SEED = 20261107
OUT = Path(__file__).with_name("tickets.jsonl")

NAMES = ["Maria Lopez", "James Carter", "Aisha Khan", "Diego Ramirez", "Emily Chen", "Noah Patel"]
EMAILS = ["maria.lopez@example.com", "jcarter88@example.net", "aisha.k@example.org", "d.ramirez@example.com"]
PHONES = ["(305) 555-0142", "786-555-0199", "+1 954 555 0123"]
CARDS = ["4111 1111 1111 1111", "5500-0000-0000-0004"]
ADDRESSES = ["1200 Brickell Bay Drive", "42 Ocean Ave", "88 Coral Way"]

# (category, urgency, template, kb_file, kb_fact)
TEMPLATES = [
    ("billing", "low", "Hi, how long does a refund take to arrive after I request it?", "billing.md", "5 to 10 business days"),
    ("billing", "medium", "I was charged twice for the same invoice this month. Can you fix it?", "billing.md", "3 business days"),
    ("billing", "high", "Someone used my card {card} for charges I did not make. This is fraud, please block it now!", None, None),
    ("billing", "low", "Where can I download my invoices as PDF?", "billing.md", "Settings > Billing > Invoices"),
    ("account", "medium", "I can't log in, the password reset link says it's expired.", "account.md", "1 hour"),
    ("account", "medium", "I lost my phone and can't pass 2FA. What do I do?", "account.md", "backup codes"),
    ("account", "low", "How do I change the email address on my account?", "account.md", "Settings > Account"),
    ("account", "high", "My account was hacked and someone changed my email to theirs. Lock it immediately!", None, None),
    ("technical", "high", "The whole service is down for our team of 200 people, total outage since 9am!", None, None),
    ("technical", "low", "What does error 429 Too Many Requests mean?", "technical.md", "100 requests per minute"),
    ("technical", "medium", "File upload keeps failing with error 500, the file is 3 GB.", "technical.md", "2 GB"),
    ("technical", "medium", "Sync stopped working on my laptop since yesterday.", "technical.md", "Clear cache"),
    ("shipping", "low", "How long does standard shipping take?", "shipping.md", "3 to 5 business days"),
    ("shipping", "medium", "Tracking says delivered but there is no package at {address}.", "shipping.md", "48 hours"),
    ("shipping", "low", "Can I return an unused router I bought two weeks ago?", "shipping.md", "30 days"),
    ("feedback", "low", "Just wanted to say the new dashboard is fantastic, great job team!", None, None),
    ("feedback", "low", "Suggestion: please add a dark mode to the mobile app.", None, None),
    ("other", "low", "Do you have any job openings in Miami?", None, None),
]

PII_WRAPPERS = [
    ("This is {name}. ", ""),
    ("", " You can reach me at {email}."),
    ("", " Call me back at {phone}."),
    ("Hello, {name} here. ", " My email is {email} and phone {phone}."),
]


def generate(n: int = 40) -> list[dict]:
    rng = random.Random(SEED)
    rows = []
    for i in range(n):
        cat, urg, tpl, kb_file, kb_fact = TEMPLATES[i % len(TEMPLATES)]
        values = {
            "name": rng.choice(NAMES), "email": rng.choice(EMAILS), "phone": rng.choice(PHONES),
            "card": rng.choice(CARDS), "address": rng.choice(ADDRESSES),
        }
        planted = [values[k] for k in ("card", "address") if "{" + k + "}" in tpl]
        body = tpl
        if i % 2 == 0:  # half the tickets get extra PII
            pre, post = PII_WRAPPERS[(i // 2) % len(PII_WRAPPERS)]
            body = pre + tpl + post
            planted += [values[k] for k in ("name", "email", "phone") if "{" + k + "}" in pre + post]
        rows.append({
            "ticket_id": f"eval-{i:03d}",
            "subject": "",
            "body": body.format(**values),
            "category": cat,
            "urgency": urg,
            "contains_pii": bool(planted),
            "pii": planted,
            "kb_file": kb_file,
            "kb_fact": kb_fact,
        })
    return rows


if __name__ == "__main__":
    rows = generate()
    OUT.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    print(f"wrote {len(rows)} tickets to {OUT}")
