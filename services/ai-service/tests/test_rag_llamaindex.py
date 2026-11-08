"""Exercise the real LlamaIndex pipeline with LlamaIndex's own mock LLM/embeddings (no Ollama)."""
from pathlib import Path

from llama_index.core.embeddings import MockEmbedding
from llama_index.core.llms import MockLLM

from app.rag import LlamaIndexRAG

DOCS = Path(__file__).resolve().parents[3] / "docs"


def test_index_and_query_returns_sources():
    rag = LlamaIndexRAG(DOCS, llm=MockLLM(max_tokens=8), embed_model=MockEmbedding(embed_dim=8))
    ans = rag.answer("How do I get a refund?", top_k=2)
    assert len(ans.sources) == 2
    assert all(s.file.endswith(".md") for s in ans.sources)
    assert isinstance(ans.answer, str)
