"""FastAPI app: reusable AI endpoints called by n8n workflows (or anything that speaks HTTP)."""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from typing import Callable

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError

from .classify import classify
from .config import Settings
from .llm import ChatLLM, LLMError, OpenAICompatLLM
from .logging_setup import log, request_id_var, setup_logging
from .models import (
    Answer,
    AnswerIn,
    Classification,
    RedactionResult,
    RoutingDecision,
    TextIn,
    TicketEvent,
    TicketRecord,
)
from .rag import Answerer, build_ollama_rag
from .redact import redact
from .routing import decide, is_no_answer
from .security import verify
from .store import TicketStore

logger = logging.getLogger("ai_service")


@dataclass
class Deps:
    settings: Settings
    llm: ChatLLM
    answerer_factory: Callable[[], Answerer]
    store: TicketStore
    _answerer: Answerer | None = None

    @property
    def answerer(self) -> Answerer:
        # Built lazily: indexing embeds every doc, so don't pay for it at import/startup.
        if self._answerer is None:
            self._answerer = self.answerer_factory()
        return self._answerer


def default_deps(settings: Settings | None = None) -> Deps:
    s = settings or Settings()
    timeout = float(s.llm_timeout_s)
    return Deps(
        settings=s,
        llm=OpenAICompatLLM(s.llm_base_url, s.llm_model, timeout),
        answerer_factory=lambda: build_ollama_rag(s.docs_dir, s.ollama_native_url, s.llm_model, s.embed_model, timeout),
        store=TicketStore(s.db_path),
    )


def create_app(deps: Deps | None = None) -> FastAPI:
    setup_logging()
    d = deps or default_deps()
    app = FastAPI(title="ai-ops-automation ai-service", version="0.1.0")
    app.state.deps = d
    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_methods=["*"], allow_headers=["*"])

    @app.middleware("http")
    async def request_id_mw(request: Request, call_next):
        rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        token = request_id_var.set(rid)
        t0 = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        ms = round((time.perf_counter() - t0) * 1000, 1)
        token = request_id_var.set(rid)
        log(logger, "request", method=request.method, path=request.url.path, status=response.status_code, ms=ms)
        request_id_var.reset(token)
        response.headers["X-Request-ID"] = rid
        return response

    def llm_or_502(fn, *args):
        try:
            return fn(*args)
        except (LLMError, ValidationError) as e:
            raise HTTPException(status_code=502, detail=f"upstream LLM error: {e}") from e

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "model": d.settings.llm_model}

    @app.post("/classify", response_model=Classification)
    def classify_ep(body: TextIn) -> Classification:
        return llm_or_502(classify, body.text, d.llm)

    @app.post("/redact", response_model=RedactionResult)
    def redact_ep(body: TextIn, llm_pass: bool = Query(default=True)) -> RedactionResult:
        use_llm = llm_pass and d.settings.llm_redact_pass == "1"
        return redact(body.text, d.llm if use_llm else None)

    @app.post("/answer", response_model=Answer)
    def answer_ep(body: AnswerIn) -> Answer:
        try:
            return d.answerer.answer(body.question, body.top_k)
        except Exception as e:  # LlamaIndex/Ollama errors are not typed consistently
            logger.exception("rag failed")
            raise HTTPException(status_code=502, detail=f"RAG error: {type(e).__name__}") from e

    @app.post("/webhook/ticket", response_model=RoutingDecision)
    async def ticket_webhook(request: Request) -> RoutingDecision:
        raw = await request.body()
        if not verify(d.settings.webhook_secret, request.headers.get("X-Timestamp"), request.headers.get("X-Signature"), raw):
            raise HTTPException(status_code=401, detail="invalid signature")
        try:
            event = TicketEvent.model_validate_json(raw)
        except ValidationError as e:
            raise HTTPException(status_code=422, detail=e.errors(include_url=False, include_input=False, include_context=False)) from e
        return process_ticket(event)

    def process_ticket(event: TicketEvent) -> RoutingDecision:
        text = f"{event.subject}\n\n{event.body}".strip()
        # 1) Redact first: nothing downstream (LLM, logs, DB, n8n) sees raw PII.
        red = redact(text, d.llm if d.settings.llm_redact_pass == "1" else None)
        # 2) Classify the redacted text.
        cls = llm_or_502(classify, red.redacted, d.llm)
        # 3) Try a knowledge-base answer unless it's going straight to a human.
        ans: Answer | None = None
        if cls.urgency != "high":
            try:
                ans = d.answerer.answer(red.redacted)
            except Exception:
                logger.exception("rag failed; routing without answer")
        route, reason = decide(cls, ans.answer if ans else None)
        decision = RoutingDecision(
            ticket_id=event.ticket_id,
            route=route,
            reason=reason,
            classification=cls,
            redacted_text=red.redacted,
            pii_counts=red.counts,
            suggested_reply=None if ans is None or is_no_answer(ans.answer) else ans.answer,
            sources=ans.sources if ans else [],
            request_id=request_id_var.get(),
        )
        d.store.save(decision)
        log(logger, "ticket routed", ticket_id=event.ticket_id, route=route, category=cls.category,
            urgency=cls.urgency, pii=red.counts)
        return decision

    app.state.process_ticket = process_ticket

    @app.get("/tickets", response_model=list[TicketRecord])
    def list_tickets(limit: int = Query(100, ge=1, le=1000), since: str | None = None) -> list[TicketRecord]:
        return d.store.list(limit, since)

    @app.get("/tickets/digest")
    def digest(since: str | None = None) -> dict:
        rows = d.store.list(1000, since)
        by = lambda key: {k: sum(1 for r in rows if key(r) == k) for k in sorted({key(r) for r in rows})}  # noqa: E731
        return {
            "since": since,
            "total": len(rows),
            "by_route": by(lambda r: r.route),
            "by_category": by(lambda r: r.classification.category),
            "by_urgency": by(lambda r: r.classification.urgency),
            "escalated": [{"ticket_id": r.ticket_id, "reason": r.reason} for r in rows if r.route == "escalate"],
        }

    return app


def get_app() -> FastAPI:  # uvicorn --factory app.main:get_app
    return create_app()
