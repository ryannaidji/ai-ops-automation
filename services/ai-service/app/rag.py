"""RAG over docs/*.md with LlamaIndex (Ollama LLM + nomic-embed-text embeddings)."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Protocol

from llama_index.core import PromptTemplate, SimpleDirectoryReader, VectorStoreIndex
from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.core.llms import LLM
from llama_index.core.node_parser import MarkdownNodeParser

from .models import Answer, Source

logger = logging.getLogger(__name__)

NO_ANSWER = "I don't know based on the knowledge base."

QA_PROMPT = PromptTemplate(
    "You are a support assistant. Answer ONLY from the context below. If the context does not "
    f'contain the answer, reply exactly "{NO_ANSWER}" Keep it under 80 words.\n'
    "Context:\n{context_str}\n\nQuestion: {query_str}\nAnswer:"
)


class Answerer(Protocol):
    def answer(self, question: str, top_k: int = 3) -> Answer: ...


class LlamaIndexRAG:
    def __init__(self, docs_dir: Path | str, llm: LLM, embed_model: BaseEmbedding):
        self.llm = llm
        docs = SimpleDirectoryReader(str(docs_dir), required_exts=[".md"], recursive=True).load_data()
        nodes = MarkdownNodeParser().get_nodes_from_documents(docs)
        self.index = VectorStoreIndex(nodes, embed_model=embed_model)
        logger.info("rag index built", extra={"fields": {"docs": len(docs), "nodes": len(nodes)}})

    def answer(self, question: str, top_k: int = 3) -> Answer:
        engine = self.index.as_query_engine(llm=self.llm, similarity_top_k=top_k, text_qa_template=QA_PROMPT)
        resp = engine.query(question)
        sources = [
            Source(
                file=Path(n.node.metadata.get("file_name", "?")).name,
                score=n.score,
                snippet=n.node.get_content()[:240],
            )
            for n in resp.source_nodes
        ]
        return Answer(answer=str(resp).strip(), sources=sources)


def build_ollama_rag(docs_dir: str, native_url: str, llm_model: str, embed_model: str, timeout: float) -> LlamaIndexRAG:
    from llama_index.embeddings.ollama import OllamaEmbedding
    from llama_index.llms.ollama import Ollama

    llm = Ollama(model=llm_model, base_url=native_url, request_timeout=timeout, temperature=0)
    emb = OllamaEmbedding(model_name=embed_model, base_url=native_url)
    return LlamaIndexRAG(docs_dir, llm, emb)
