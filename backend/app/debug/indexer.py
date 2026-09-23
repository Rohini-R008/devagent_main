"""
Indexes a repo's Python source into ChromaDB so the debugger can retrieve
relevant code context for a given error traceback (RAG).

Uses OpenAI embeddings for consistency with the rest of the stack (no extra
local model download needed).
"""
import hashlib
import logging
import os
from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions

from app.config import settings

logger = logging.getLogger("devagent.debug.indexer")

CHROMA_DIR = str(Path(__file__).resolve().parents[3] / "chroma_db")
CHUNK_SIZE = 1500       # characters per chunk
CHUNK_OVERLAP = 200

_client = None


def get_chroma_client() -> chromadb.ClientAPI:
    global _client
    if _client is None:
        os.makedirs(CHROMA_DIR, exist_ok=True)
        _client = chromadb.PersistentClient(path=CHROMA_DIR)
    return _client


def _embedding_fn():
    return embedding_functions.DefaultEmbeddingFunction()


def collection_name_for(repo_path: str) -> str:
    """Stable, valid Chroma collection name derived from the repo path."""
    digest = hashlib.sha256(os.path.abspath(repo_path).encode()).hexdigest()[:16]
    return f"repo_{digest}"


def _chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP):
    """Yield (chunk, start_line) pairs, approximating line numbers by newline count."""
    lines = text.splitlines(keepends=True)
    chunk, chunk_start_line, char_count = [], 1, 0

    for i, line in enumerate(lines, start=1):
        chunk.append(line)
        char_count += len(line)
        if char_count >= chunk_size:
            yield "".join(chunk), chunk_start_line
            # keep a small overlap by re-including the tail of this chunk
            overlap_lines = max(1, int(len(chunk) * (overlap / chunk_size)))
            chunk = chunk[-overlap_lines:]
            chunk_start_line = i - overlap_lines + 1
            char_count = sum(len(l) for l in chunk)

    if chunk:
        yield "".join(chunk), chunk_start_line


def index_repo(repo_path: str, collection_name: str | None = None) -> dict:
    """Walk all .py files under repo_path, chunk + embed + store them."""
    collection_name = collection_name or collection_name_for(repo_path)
    client = get_chroma_client()

    # Fresh index each time — simplest correct behavior for a repo that changes.
    try:
        client.delete_collection(collection_name)
    except Exception:
        pass
    collection = client.create_collection(collection_name, embedding_function=_embedding_fn())

    documents, metadatas, ids = [], [], []
    file_count = 0

    for path in Path(repo_path).rglob("*.py"):
        if any(part in {".venv", "venv", "node_modules", "__pycache__", ".git"} for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if not text.strip():
            continue

        rel_path = str(path.relative_to(repo_path))
        file_count += 1

        for chunk_idx, (chunk, start_line) in enumerate(_chunk_text(text)):
            documents.append(chunk)
            metadatas.append({"file": rel_path, "start_line": start_line})
            ids.append(f"{rel_path}::{chunk_idx}::{start_line}")

    if documents:
        # Chroma has a practical batch-size ceiling; chunk the upsert.
        batch_size = 100
        for i in range(0, len(documents), batch_size):
            collection.add(
                documents=documents[i:i + batch_size],
                metadatas=metadatas[i:i + batch_size],
                ids=ids[i:i + batch_size],
            )

    logger.info("Indexed %d files / %d chunks into %s", file_count, len(documents), collection_name)
    return {"collection_name": collection_name, "files_indexed": file_count, "chunks_indexed": len(documents)}


def query_context(collection_name: str, query_text: str, n_results: int = 6) -> list[dict]:
    """Retrieve the most relevant code chunks for a query (e.g. a traceback)."""
    client = get_chroma_client()
    try:
        collection = client.get_collection(collection_name, embedding_function=_embedding_fn())
    except Exception as e:
        raise ValueError(f"No index found for '{collection_name}'. Run index_repo() first.") from e

    result = collection.query(query_texts=[query_text], n_results=n_results)

    hits = []
    docs = result.get("documents", [[]])[0]
    metas = result.get("metadatas", [[]])[0]
    for doc, meta in zip(docs, metas):
        hits.append({"file": meta.get("file"), "start_line": meta.get("start_line"), "text": doc})
    return hits