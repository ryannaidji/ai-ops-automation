"""HMAC-SHA256 webhook signatures.

Sender sets `X-Timestamp: <unix seconds>` and `X-Signature: sha256=<hex>` where the MAC
covers `<timestamp>.<raw body>`. The timestamp window blocks replays."""
from __future__ import annotations

import hashlib
import hmac
import time

MAX_SKEW_S = 300


def sign(secret: str, timestamp: str, body: bytes) -> str:
    mac = hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256)
    return "sha256=" + mac.hexdigest()


def verify(secret: str, timestamp: str | None, signature: str | None, body: bytes, now: float | None = None) -> bool:
    if not timestamp or not signature:
        return False
    try:
        ts = int(timestamp)
    except ValueError:
        return False
    current = time.time() if now is None else now
    if abs(current - ts) > MAX_SKEW_S:
        return False
    return hmac.compare_digest(sign(secret, timestamp, body), signature)
