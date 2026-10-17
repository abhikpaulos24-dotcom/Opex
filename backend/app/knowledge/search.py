"""Factory memory search over SOPs, manuals, uploaded documents and technician notes.

Hybrid retrieval: TF-IDF keyword scores always; Gemini embeddings (gemini-embedding-001,
768 dimensions) added when Gemini is configured. The corpus is a few thousand chunks, so an
in-memory index answers in milliseconds; past ~100k chunks, move vectors to pgvector.
"""

import hashlib
import json
import logging
import re
import threading
from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer

from app.ai import gemini
from app.core.paths import KNOWLEDGE_DIR, MODELS_DIR, PROCESSED_DIR

log = logging.getLogger(__name__)
EMBED_CACHE = MODELS_DIR / "knowledge_embeddings.json"


@dataclass
class Chunk:
    doc_id: str
    title: str
    section: str
    kind: str
    text: str


class KnowledgeIndex:
    def __init__(self):
        self.lock = threading.Lock()
        self.extra_docs: list[tuple[str, str, str, str]] = []  # (id, kind, title, body) from the database
        self.chunks: list[Chunk] = []
        self.vectorizer = None
        self.matrix = None
        self.embeddings: np.ndarray | None = None

    def set_extra_documents(self, docs: list[tuple[str, str, str, str]]) -> None:
        self.extra_docs = docs
        self.build()

    def build(self) -> None:
        chunks = []
        for path in sorted(KNOWLEDGE_DIR.rglob("*.md")):
            if path.name == "README.md":
                continue
            kind = "sop" if "sops" in path.parts else "manual"
            chunks.extend(_split_markdown(path.stem, path.read_text(), kind))
        for doc_id, kind, title, body in self.extra_docs:
            chunks.extend(_split_markdown(doc_id, f"# {title}\n{body}", kind))
        history = PROCESSED_DIR / "maintenance_history.csv"
        if history.exists():
            log_df = pd.read_csv(history)
            for row in log_df[log_df["work_type"] == "unplanned"].itertuples():
                chunks.append(
                    Chunk(
                        f"log-{row.Index}",
                        f"{row.machine_id} breakdown {row.date[:10]}",
                        row.component,
                        "maintenance_log",
                        f"{row.machine_id} {row.parts}: {row.technician_note} "
                        f"(downtime {row.duration_h} h, cost ₹{row.cost_inr:,.0f})",
                    )
                )
        with self.lock:
            self.chunks = chunks
            self.vectorizer = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, stop_words="english")
            self.matrix = self.vectorizer.fit_transform([f"{c.title} {c.section} {c.text}" for c in chunks])
            self.embeddings = None
        log.info("knowledge index: %d chunks", len(chunks))
        if gemini.enabled():
            threading.Thread(target=self._embed_all, daemon=True).start()

    def _embed_all(self) -> None:
        texts = [f"{c.title}. {c.section}. {c.text}"[:2000] for c in self.chunks]
        keys = [hashlib.sha1(t.encode()).hexdigest() for t in texts]
        cache = json.loads(EMBED_CACHE.read_text()) if EMBED_CACHE.exists() else {}
        missing = [i for i, k in enumerate(keys) if k not in cache]
        if missing:
            vectors = gemini.embed([texts[i] for i in missing])
            if vectors is None:
                return
            for i, v in zip(missing, vectors, strict=False):
                cache[keys[i]] = v
            EMBED_CACHE.write_text(json.dumps(cache))
        matrix = np.array([cache[k] for k in keys], dtype=np.float32)
        with self.lock:
            self.embeddings = matrix / np.linalg.norm(matrix, axis=1, keepdims=True)
        log.info("knowledge index: Gemini embeddings ready (%d)", len(keys))

    def search(self, query: str, limit: int = 5, kinds: tuple[str, ...] | None = None) -> list[dict]:
        if self.vectorizer is None:
            self.build()
        with self.lock:
            scores = (self.matrix @ self.vectorizer.transform([query]).T).toarray().ravel()
            embeddings = self.embeddings
            chunks = self.chunks
        method = "keyword"
        if embeddings is not None:
            q = gemini.embed([query], task="RETRIEVAL_QUERY")
            if q:
                qv = np.array(q[0], dtype=np.float32)
                scores = 0.4 * scores / max(scores.max(), 1e-9) + 0.6 * (embeddings @ (qv / np.linalg.norm(qv)))
                method = "hybrid (keyword + Gemini embeddings)"
        order = np.argsort(-scores)
        results = []
        for i in order:
            if kinds and chunks[i].kind not in kinds:
                continue
            if scores[i] <= 0.01:
                break
            c = chunks[i]
            results.append(
                {
                    "doc_id": c.doc_id,
                    "title": c.title,
                    "section": c.section,
                    "kind": c.kind,
                    "text": c.text,
                    "score": round(float(scores[i]), 3),
                    "method": method,
                }
            )
            if len(results) >= limit:
                break
        return results


def _split_markdown(doc_id: str, text: str, kind: str) -> list[Chunk]:
    title_match = re.search(r"^# (.+)$", text, re.M)
    title = title_match.group(1).strip() if title_match else doc_id
    chunks = []
    for part in re.split(r"^## ", text, flags=re.M)[1:]:
        section, _, body = part.partition("\n")
        if body.strip():
            chunks.append(Chunk(doc_id, title, section.strip(), kind, body.strip()))
    if not chunks:
        chunks.append(Chunk(doc_id, title, "", kind, text.strip()))
    return chunks


_index = KnowledgeIndex()


def get_index() -> KnowledgeIndex:
    return _index
