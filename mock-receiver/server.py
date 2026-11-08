"""Mock receiver for outbound webhooks (stands in for Discord/Slack/any HTTP sink).

Stdlib only. Every POST body is appended to a JSONL file and echoed on stdout.
  python mock-receiver/server.py            # listens on :9000
  GET  /received   -> last 50 messages as JSON
  POST /<anything> -> 204, stored
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

OUT = Path(os.getenv("MOCK_OUT", Path(__file__).resolve().parents[1] / "data" / "mock_received.jsonl"))


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        raw = self.rfile.read(int(self.headers.get("Content-Length", 0) or 0))
        try:
            body = json.loads(raw or b"null")
        except json.JSONDecodeError:
            body = raw.decode(errors="replace")
        rec = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "path": self.path, "body": body}
        OUT.parent.mkdir(parents=True, exist_ok=True)
        with OUT.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
        print(json.dumps(rec), flush=True)
        self.send_response(204)
        self.end_headers()

    def do_GET(self):  # noqa: N802
        if self.path.rstrip("/") != "/received":
            self.send_response(404)
            self.end_headers()
            return
        lines = OUT.read_text(encoding="utf-8").splitlines()[-50:] if OUT.exists() else []
        data = json.dumps([json.loads(x) for x in lines]).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


def main(port: int = 9000) -> None:
    print(f"mock receiver on :{port}, writing {OUT}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else int(os.getenv("PORT", "9000")))
