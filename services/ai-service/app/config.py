"""Settings from environment variables (no secrets in code)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _env(name: str, default: str):
    return field(default_factory=lambda: os.getenv(name, default))


@dataclass(frozen=True)
class Settings:
    llm_base_url: str = _env("LLM_BASE_URL", "http://localhost:11434/v1")
    llm_model: str = _env("LLM_MODEL", "qwen2.5:3b")
    embed_model: str = _env("EMBED_MODEL", "nomic-embed-text")
    llm_timeout_s: str = _env("LLM_TIMEOUT_S", "120")
    webhook_secret: str = _env("WEBHOOK_SECRET", "dev-secret-change-me")
    docs_dir: str = _env("DOCS_DIR", str(ROOT / "docs"))
    db_path: str = _env("DB_PATH", str(ROOT / "data" / "tickets.db"))
    llm_redact_pass: str = _env("LLM_REDACT_PASS", "1")

    @property
    def ollama_native_url(self) -> str:
        """LlamaIndex's Ollama classes use the native API (no /v1 suffix)."""
        url = self.llm_base_url.rstrip("/")
        return url[:-3] if url.endswith("/v1") else url
