"""SQLite store for processed tickets. Only redacted text is ever stored."""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from .models import RoutingDecision, TicketRecord


class TicketStore:
    def __init__(self, path: str):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.lock = threading.Lock()
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS tickets "
            "(ticket_id TEXT PRIMARY KEY, created_at TEXT, route TEXT, data TEXT)"
        )

    def save(self, d: RoutingDecision) -> TicketRecord:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        rec = TicketRecord(**d.model_dump(), created_at=now)
        with self.lock:
            self.conn.execute(
                "INSERT OR REPLACE INTO tickets VALUES (?,?,?,?)",
                (rec.ticket_id, rec.created_at, rec.route, rec.model_dump_json()),
            )
            self.conn.commit()
        return rec

    def list(self, limit: int = 100, since: str | None = None) -> list[TicketRecord]:
        q, args = "SELECT data FROM tickets", []
        if since:
            q += " WHERE created_at >= ?"
            args.append(since)
        q += " ORDER BY created_at DESC LIMIT ?"
        args.append(limit)
        with self.lock:
            rows = self.conn.execute(q, args).fetchall()
        return [TicketRecord.model_validate(json.loads(r[0])) for r in rows]
