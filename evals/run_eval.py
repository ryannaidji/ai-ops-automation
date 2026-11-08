"""Evaluate the triage pipeline against evals/tickets.jsonl using the REAL local Ollama models.

  python evals/run_eval.py                         # all 40, in-process app
  python evals/run_eval.py --limit 12 --thresholds evals/thresholds-ci.json

Metrics:
  category/urgency accuracy + macro-F1 (from /webhook/ticket classification)
  PII recall    = planted PII strings absent from redacted_text / planted strings
  PII precision = redacted spans overlapping a planted string / all spans (via /redact)
  RAG groundedness (KB tickets, via /answer):
      fact_hit   = expected fact phrase in answer
      source_hit = expected doc among retrieved sources
      lexical    = share of answer content words found in retrieved snippets
  latency p50/p95 of /webhook/ticket (ms)
Writes evals/results/latest.json; exits 1 if any metric < threshold.
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "services" / "ai-service"))
sys.path.insert(0, str(HERE))

STOP = set("the a an and or to of in on for is are be it this that you your with at by as from can if not".split())


def macro_f1(gold: list[str], pred: list[str]) -> float:
    labels = sorted(set(gold) | set(pred))
    f1s = []
    for lab in labels:
        tp = sum(g == p == lab for g, p in zip(gold, pred))
        fp = sum(p == lab and g != lab for g, p in zip(gold, pred))
        fn = sum(g == lab and p != lab for g, p in zip(gold, pred))
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        f1s.append(2 * prec * rec / (prec + rec) if prec + rec else 0.0)
    return sum(f1s) / len(f1s) if f1s else 0.0


def pct(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    return s[min(len(s) - 1, round(q * (len(s) - 1)))]


def words(t: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", t.lower()) if w not in STOP and len(w) > 2}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="evaluate only the first N tickets")
    ap.add_argument("--thresholds", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=HERE / "results" / "latest.json")
    args = ap.parse_args()

    import os

    os.environ.setdefault("DB_PATH", ":memory:")
    os.environ.setdefault("WEBHOOK_SECRET", "eval-secret")
    from fastapi.testclient import TestClient

    from app.main import create_app
    from app.security import sign
    from generate import generate

    rows = generate()
    if args.limit:
        rows = rows[: args.limit]
    client = TestClient(create_app())
    secret = os.environ["WEBHOOK_SECRET"]

    gold_c, pred_c, gold_u, pred_u, lat = [], [], [], [], []
    planted_total = planted_hit = spans_total = spans_ok = 0
    fact_hits, source_hits, lexical = [], [], []
    per_ticket = []

    for r in rows:
        payload = json.dumps({"ticket_id": r["ticket_id"], "subject": r["subject"], "body": r["body"]}).encode()
        ts = str(int(time.time()))
        t0 = time.perf_counter()
        resp = client.post("/webhook/ticket", content=payload,
                           headers={"X-Timestamp": ts, "X-Signature": sign(secret, ts, payload)})
        lat.append((time.perf_counter() - t0) * 1000)
        if resp.status_code != 200:
            print(f"{r['ticket_id']}: HTTP {resp.status_code} {resp.text[:200]}", file=sys.stderr)
            pred_c.append("ERROR"); pred_u.append("ERROR")  # noqa: E702
            gold_c.append(r["category"]); gold_u.append(r["urgency"])  # noqa: E702
            continue
        d = resp.json()
        gold_c.append(r["category"]); pred_c.append(d["classification"]["category"])  # noqa: E702
        gold_u.append(r["urgency"]); pred_u.append(d["classification"]["urgency"])  # noqa: E702

        # PII recall on the webhook output
        for s in r["pii"]:
            planted_total += 1
            planted_hit += s not in d["redacted_text"]
        # PII precision via /redact spans
        red = client.post("/redact", json={"text": r["body"]}).json()
        for e in red["entities"]:
            spans_total += 1
            spans_ok += any(
                e["start"] < (i := r["body"].find(s)) + len(s) and i < e["end"] for s in r["pii"] if s in r["body"]
            )

        if r["kb_file"]:
            a = client.post("/answer", json={"question": r["body"]}).json()
            ans = a.get("answer", "")
            fact_hits.append(float(r["kb_fact"].lower() in ans.lower()))
            source_hits.append(float(any(s["file"] == r["kb_file"] for s in a.get("sources", []))))
            aw = words(ans)
            ctx = words(" ".join(s["snippet"] for s in a.get("sources", [])))
            lexical.append(len(aw & ctx) / len(aw) if aw else 0.0)

        per_ticket.append({"ticket_id": r["ticket_id"], "route": d["route"], "gold": [r["category"], r["urgency"]],
                           "pred": [d["classification"]["category"], d["classification"]["urgency"]]})
        print(f"{r['ticket_id']}: {per_ticket[-1]['pred']} gold={per_ticket[-1]['gold']} route={d['route']}")

    mean = lambda xs: statistics.fmean(xs) if xs else 0.0  # noqa: E731
    metrics = {
        "n": len(rows),
        "category_accuracy": mean([float(g == p) for g, p in zip(gold_c, pred_c)]),
        "category_macro_f1": macro_f1(gold_c, pred_c),
        "urgency_accuracy": mean([float(g == p) for g, p in zip(gold_u, pred_u)]),
        "urgency_macro_f1": macro_f1(gold_u, pred_u),
        "pii_recall": planted_hit / planted_total if planted_total else 1.0,
        "pii_precision": spans_ok / spans_total if spans_total else 1.0,
        "rag_fact_hit": mean(fact_hits),
        "rag_source_hit": mean(source_hits),
        "rag_lexical_groundedness": mean(lexical),
        "latency_p50_ms": pct(lat, 0.50),
        "latency_p95_ms": pct(lat, 0.95),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"metrics": metrics, "tickets": per_ticket}, indent=2), encoding="utf-8")
    print(json.dumps(metrics, indent=2))

    if args.thresholds:
        th = json.loads(args.thresholds.read_text())
        failed = []
        for k, v in th.items():
            if k.startswith("max_"):
                if metrics[k[4:]] > v:
                    failed.append(f"{k[4:]}={metrics[k[4:]]:.3f} > {v}")
            elif metrics[k] < v:
                failed.append(f"{k}={metrics[k]:.3f} < {v}")
        if failed:
            print("THRESHOLD FAILURES:\n  " + "\n  ".join(failed))
            return 1
        print("all thresholds met")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
