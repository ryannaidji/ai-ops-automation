"""Smoke test against the real local Ollama: 2 signed tickets through /webhook/ticket, in-process."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "ai-service"))
os.environ.setdefault("DB_PATH", ":memory:")
os.environ.setdefault("WEBHOOK_SECRET", "smoke-secret")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import create_app  # noqa: E402
from app.security import sign  # noqa: E402

TICKETS = [
    {"ticket_id": "smoke-1", "subject": "Password reset",
     "body": "Hi, this is Maria Lopez (maria.lopez@example.com, 305-555-0142). "
             "My password reset link says it has expired. How long is it valid?"},
    {"ticket_id": "smoke-2", "subject": "OUTAGE",
     "body": "The whole service is down for our 200-person team since 9am. Card on file 4111 1111 1111 1111. Fix this now!"},
]

client = TestClient(create_app())
secret = os.environ["WEBHOOK_SECRET"]
for t in TICKETS:
    raw = json.dumps(t).encode()
    ts = str(int(time.time()))
    t0 = time.perf_counter()
    r = client.post("/webhook/ticket", content=raw, headers={"X-Timestamp": ts, "X-Signature": sign(secret, ts, raw)})
    ms = (time.perf_counter() - t0) * 1000
    d = r.json()
    if r.status_code == 200:
        d["sources"] = [s["file"] for s in d["sources"]]
    print(f"--- {t['ticket_id']} HTTP {r.status_code} in {ms:.0f} ms")
    print(json.dumps(d, indent=2))
