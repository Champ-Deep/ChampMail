"""
Campaign Documents RAG Service — SOLID architecture.

Ingests reference documents (docx, txt, pdf) into ChampGraph and builds
a keyword index for fast retrieval during email generation.

Architecture (SOLID):
  - DocumentParser (Interface + implementations) — OCP/LSP
  - DocumentChunker — SRP: splits text into semantic chunks
  - KeywordIndex — SRP: builds TF-based keyword index, searches by query
  - CampaignDocsRepository — SRP: persists doc metadata + chunks to JSON store
  - CampaignDocsService — ISP facade: orchestrates parse → chunk → index → ingest
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Data classes
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class DocumentChunk:
    """A single chunk of a parsed document."""
    doc_id: str
    chunk_index: int
    heading: str
    text: str
    keywords: list[str] = field(default_factory=list)

    @property
    def content(self) -> str:
        if self.heading:
            return f"{self.heading}\n{self.text}"
        return self.text


@dataclass
class DocumentMeta:
    """Metadata for an ingested document."""
    doc_id: str
    filename: str
    source_path: str
    file_hash: str
    doc_type: str  # "docx", "txt", "pdf"
    ingested_at: str
    chunk_count: int
    graph_account: str
    title: str = ""
    keywords: list[str] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# DocumentParser — Interface + Implementations (OCP / LSP)
# ─────────────────────────────────────────────────────────────────────────────

class DocumentParser(ABC):
    """Abstract parser — one implementation per file type."""

    @abstractmethod
    def can_parse(self, file_path: str) -> bool:
        """Return True if this parser handles the given file."""

    @abstractmethod
    def parse(self, file_path: str) -> list[tuple[str, str]]:
        """
        Parse a file into a list of (heading, paragraph_text) tuples.
        Heading may be empty for body paragraphs.
        """


class DocxParser(DocumentParser):
    """Parses .docx files using python-docx."""

    def can_parse(self, file_path: str) -> bool:
        return file_path.lower().endswith(".docx")

    def parse(self, file_path: str) -> list[tuple[str, str]]:
        from docx import Document
        doc = Document(file_path)
        sections: list[tuple[str, str]] = []
        current_heading = ""

        for para in doc.paragraphs:
            text = para.text.strip()
            if not text:
                continue

            style = para.style
            style_name = (style.name if style and style.name else "").lower()
            if "heading" in style_name or (
                para.runs and para.runs[0].bold and len(text) < 120
            ):
                current_heading = text
            else:
                sections.append((current_heading, text))

        return sections


class TxtParser(DocumentParser):
    """Parses plain text files — headings detected by ALL CAPS or short bold-like lines."""

    def can_parse(self, file_path: str) -> bool:
        return file_path.lower().endswith(".txt")

    def parse(self, file_path: str) -> list[tuple[str, str]]:
        with open(file_path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

        sections: list[tuple[str, str]] = []
        current_heading = ""

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            # Heuristic: short ALL-CAPS lines are headings
            if stripped.isupper() and len(stripped) < 100:
                current_heading = stripped
            elif len(stripped) < 80 and stripped.endswith(":"):
                current_heading = stripped.rstrip(":")
            else:
                sections.append((current_heading, stripped))

        return sections


class PdfParser(DocumentParser):
    """Parses PDF files — requires PyPDF2 or falls back to error."""

    def can_parse(self, file_path: str) -> bool:
        return file_path.lower().endswith(".pdf")

    def parse(self, file_path: str) -> list[tuple[str, str]]:
        try:
            from PyPDF2 import PdfReader
        except ImportError:
            raise ImportError(
                "PyPDF2 is required to parse PDF files. "
                "Install it with: pip install PyPDF2"
            )

        reader = PdfReader(file_path)
        sections: list[tuple[str, str]] = []

        for page in reader.pages:
            text = page.extract_text() or ""
            for line in text.split("\n"):
                stripped = line.strip()
                if not stripped:
                    continue
                if stripped.isupper() and len(stripped) < 100:
                    sections.append((stripped, ""))
                else:
                    heading = sections[-1][0] if sections and not sections[-1][1] else ""
                    if sections and not sections[-1][1]:
                        sections[-1] = (heading, stripped)
                    else:
                        sections.append((heading, stripped))

        return [(h, t) for h, t in sections if t]


class ParserRegistry:
    """
    Registry of document parsers — Open/Closed Principle.
    New file types are supported by registering a new parser, not modifying existing code.
    """

    def __init__(self) -> None:
        self._parsers: list[DocumentParser] = []

    def register(self, parser: DocumentParser) -> None:
        self._parsers.append(parser)

    def get_parser(self, file_path: str) -> DocumentParser:
        for parser in self._parsers:
            if parser.can_parse(file_path):
                return parser
        supported = ", ".join(
            p.__class__.__name__.replace("Parser", "").lower()
            for p in self._parsers
        )
        raise ValueError(
            f"Unsupported file type: {Path(file_path).suffix}. "
            f"Supported: {supported}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# DocumentChunker — SRP
# ─────────────────────────────────────────────────────────────────────────────

class DocumentChunker:
    """
    Splits parsed sections into semantic chunks grouped by heading.
    Merges small consecutive paragraphs under the same heading.
    """

    def __init__(self, max_chunk_size: int = 1500, overlap_sentences: int = 1):
        self._max_chunk_size = max_chunk_size
        self._overlap_sentences = overlap_sentences

    def chunk(self, doc_id: str, sections: list[tuple[str, str]]) -> list[DocumentChunk]:
        chunks: list[DocumentChunk] = []
        current_heading = ""
        current_text_parts: list[str] = []
        chunk_index = 0

        def _flush():
            nonlocal chunk_index
            if not current_text_parts:
                return
            merged = "\n".join(current_text_parts)
            # Split oversized chunks
            for sub_text in self._split_if_large(merged):
                chunks.append(DocumentChunk(
                    doc_id=doc_id,
                    chunk_index=chunk_index,
                    heading=current_heading,
                    text=sub_text.strip(),
                ))
                chunk_index += 1

        for heading, text in sections:
            if heading != current_heading and heading:
                _flush()
                current_heading = heading
                current_text_parts = [text] if text else []
            else:
                current_text_parts.append(text)

        _flush()
        return chunks

    def _split_if_large(self, text: str) -> list[str]:
        if len(text) <= self._max_chunk_size:
            return [text]

        sentences = re.split(r'(?<=[.!?])\s+', text)
        parts: list[str] = []
        current: list[str] = []
        current_len = 0

        for sent in sentences:
            if current_len + len(sent) > self._max_chunk_size and current:
                parts.append(" ".join(current))
                # Overlap: carry last N sentences forward
                current = current[-self._overlap_sentences:] if self._overlap_sentences else []
                current_len = sum(len(s) for s in current)
            current.append(sent)
            current_len += len(sent)

        if current:
            parts.append(" ".join(current))

        return parts


# ─────────────────────────────────────────────────────────────────────────────
# KeywordIndex — SRP
# ─────────────────────────────────────────────────────────────────────────────

# Common stopwords to exclude from keyword extraction
_STOPWORDS = frozenset({
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "shall", "can", "that", "this",
    "these", "those", "it", "its", "not", "no", "nor", "as", "if", "then",
    "than", "too", "very", "just", "about", "above", "after", "again",
    "all", "also", "am", "any", "because", "before", "between", "both",
    "each", "few", "get", "got", "here", "how", "into", "more", "most",
    "must", "my", "new", "now", "off", "only", "other", "our", "out",
    "over", "own", "per", "same", "she", "he", "so", "some", "such",
    "up", "us", "we", "what", "when", "where", "which", "while", "who",
    "whom", "why", "you", "your", "their", "them", "they", "through",
})


class KeywordIndex:
    """
    Builds a term-frequency keyword index over document chunks.
    Supports ranked retrieval by query terms.
    """

    def __init__(self) -> None:
        # term -> list of (doc_id, chunk_index, frequency)
        self._index: dict[str, list[tuple[str, int, int]]] = {}
        self._chunks: dict[tuple[str, int], DocumentChunk] = {}

    def add_chunk(self, chunk: DocumentChunk) -> None:
        key = (chunk.doc_id, chunk.chunk_index)
        self._chunks[key] = chunk

        terms = self._extract_terms(chunk.content)
        chunk.keywords = list(set(terms))[:30]  # store top keywords on chunk

        term_freq: dict[str, int] = {}
        for term in terms:
            term_freq[term] = term_freq.get(term, 0) + 1

        for term, freq in term_freq.items():
            if term not in self._index:
                self._index[term] = []
            self._index[term].append((chunk.doc_id, chunk.chunk_index, freq))

    def search(
        self,
        query: str,
        max_results: int = 10,
        doc_id_filter: str | None = None,
    ) -> list[DocumentChunk]:
        """
        Search chunks by query string. Returns chunks ranked by term overlap score.
        """
        query_terms = self._extract_terms(query)
        if not query_terms:
            return []

        # Score each chunk by how many query terms it contains, weighted by frequency
        scores: dict[tuple[str, int], float] = {}
        for term in query_terms:
            for doc_id, chunk_idx, freq in self._index.get(term, []):
                if doc_id_filter and doc_id != doc_id_filter:
                    continue
                key = (doc_id, chunk_idx)
                scores[key] = scores.get(key, 0) + freq

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        results: list[DocumentChunk] = []
        for key, _score in ranked[:max_results]:
            chunk = self._chunks.get(key)
            if chunk:
                results.append(chunk)

        return results

    def get_all_doc_ids(self) -> set[str]:
        return {k[0] for k in self._chunks}

    def get_chunks_by_doc(self, doc_id: str) -> list[DocumentChunk]:
        return sorted(
            [c for k, c in self._chunks.items() if k[0] == doc_id],
            key=lambda c: c.chunk_index,
        )

    @staticmethod
    def _extract_terms(text: str) -> list[str]:
        words = re.findall(r'[a-zA-Z0-9]{2,}', text.lower())
        return [w for w in words if w not in _STOPWORDS]

    def to_dict(self) -> dict:
        """Serialize index for persistence."""
        return {
            "index": {
                term: entries for term, entries in self._index.items()
            },
            "chunks": {
                f"{k[0]}:{k[1]}": asdict(v) for k, v in self._chunks.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> "KeywordIndex":
        """Deserialize index from persistence."""
        idx = cls()
        idx._index = data.get("index", {})
        for key_str, chunk_data in data.get("chunks", {}).items():
            chunk = DocumentChunk(**chunk_data)
            k = (chunk.doc_id, chunk.chunk_index)
            idx._chunks[k] = chunk
        return idx


# ─────────────────────────────────────────────────────────────────────────────
# CampaignDocsRepository — SRP (persistence)
# ─────────────────────────────────────────────────────────────────────────────

class CampaignDocsRepository:
    """
    Persists document metadata and keyword index to a JSON file store.
    Dependency Inversion: service depends on this abstraction, not file I/O directly.
    """

    def __init__(self, store_dir: str | None = None):
        if store_dir:
            self._store_dir = Path(store_dir)
        else:
            # Default: backend/data/campaign_docs/
            self._store_dir = Path(__file__).resolve().parent.parent.parent / "data" / "campaign_docs"
        self._store_dir.mkdir(parents=True, exist_ok=True)

    @property
    def _meta_path(self) -> Path:
        return self._store_dir / "docs_meta.json"

    @property
    def _index_path(self) -> Path:
        return self._store_dir / "keyword_index.json"

    def load_meta(self) -> dict[str, DocumentMeta]:
        if not self._meta_path.exists():
            return {}
        with open(self._meta_path) as f:
            raw = json.load(f)
        return {
            doc_id: DocumentMeta(**data)
            for doc_id, data in raw.items()
        }

    def save_meta(self, docs: dict[str, DocumentMeta]) -> None:
        with open(self._meta_path, "w") as f:
            json.dump({k: asdict(v) for k, v in docs.items()}, f, indent=2)

    def load_index(self) -> KeywordIndex:
        if not self._index_path.exists():
            return KeywordIndex()
        with open(self._index_path) as f:
            return KeywordIndex.from_dict(json.load(f))

    def save_index(self, index: KeywordIndex) -> None:
        with open(self._index_path, "w") as f:
            json.dump(index.to_dict(), f)

    def remove_doc(self, doc_id: str) -> None:
        docs = self.load_meta()
        docs.pop(doc_id, None)
        self.save_meta(docs)


# ─────────────────────────────────────────────────────────────────────────────
# CampaignDocsService — Facade (ISP: exposes only what callers need)
# ─────────────────────────────────────────────────────────────────────────────

class CampaignDocsService:
    """
    Orchestrates document ingestion and retrieval for campaign reference docs.

    Responsibilities:
      - Accept a file path → parse → chunk → index → ingest into ChampGraph
      - Search indexed docs by query for email generation context
      - Auto-detect campaign relevance by matching query against doc keywords
    """

    def __init__(
        self,
        repository: CampaignDocsRepository | None = None,
        chunker: DocumentChunker | None = None,
    ):
        self._repo = repository or CampaignDocsRepository()
        self._chunker = chunker or DocumentChunker()

        # Build parser registry — new formats added here (OCP)
        self._parser_registry = ParserRegistry()
        self._parser_registry.register(DocxParser())
        self._parser_registry.register(TxtParser())
        self._parser_registry.register(PdfParser())

        # Lazy-loaded index
        self._index: KeywordIndex | None = None

    @property
    def index(self) -> KeywordIndex:
        if self._index is None:
            self._index = self._repo.load_index()
        return self._index

    def _file_hash(self, file_path: str) -> str:
        h = hashlib.sha256()
        with open(file_path, "rb") as f:
            for block in iter(lambda: f.read(8192), b""):
                h.update(block)
        return h.hexdigest()[:16]

    def _make_doc_id(self, file_path: str) -> str:
        name = Path(file_path).stem
        # Normalize to a clean identifier
        clean = re.sub(r'[^a-zA-Z0-9]', '_', name).lower().strip('_')
        return clean

    # ── Ingest ───────────────────────────────────────────────────────────

    async def ingest_document(
        self,
        file_path: str,
        graph_account: str = "campaign_docs",
        title: str = "",
    ) -> DocumentMeta:
        """
        Parse, chunk, index, and ingest a document into ChampGraph.

        Args:
            file_path: Absolute or relative path to the document file.
            graph_account: ChampGraph account name for ingestion.
            title: Optional human-readable title (defaults to filename).

        Returns:
            DocumentMeta with ingestion details.
        """
        file_path = str(Path(file_path).resolve())
        if not os.path.isfile(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        # Parse
        parser = self._parser_registry.get_parser(file_path)
        sections = parser.parse(file_path)
        if not sections:
            raise ValueError(f"No content extracted from {file_path}")

        # Build doc ID and check for duplicates
        doc_id = self._make_doc_id(file_path)
        file_hash = self._file_hash(file_path)
        docs = self._repo.load_meta()

        if doc_id in docs and docs[doc_id].file_hash == file_hash:
            logger.info("Document %s already ingested with same hash, skipping.", doc_id)
            return docs[doc_id]

        # Chunk
        chunks = self._chunker.chunk(doc_id, sections)

        # Index
        index = self._repo.load_index()
        # Remove old chunks for this doc if re-ingesting
        old_chunks = index.get_chunks_by_doc(doc_id)
        if old_chunks:
            # Rebuild index without this doc's chunks
            all_chunks = [
                c for k, c in index._chunks.items() if k[0] != doc_id
            ]
            index = KeywordIndex()
            for c in all_chunks:
                index.add_chunk(c)

        for chunk in chunks:
            index.add_chunk(chunk)

        # Extract top document-level keywords
        all_text = " ".join(c.content for c in chunks)
        doc_keywords = self._extract_top_keywords(all_text, n=20)

        # Ingest into ChampGraph
        await self._ingest_to_graph(chunks, graph_account, doc_id)

        # Build metadata
        filename = Path(file_path).name
        suffix = Path(file_path).suffix.lstrip(".").lower()
        meta = DocumentMeta(
            doc_id=doc_id,
            filename=filename,
            source_path=file_path,
            file_hash=file_hash,
            doc_type=suffix,
            ingested_at=datetime.now(timezone.utc).isoformat(),
            chunk_count=len(chunks),
            graph_account=graph_account,
            title=title or filename,
            keywords=doc_keywords,
        )

        # Persist
        docs[doc_id] = meta
        self._repo.save_meta(docs)
        self._repo.save_index(index)
        self._index = index

        return meta

    async def _ingest_to_graph(
        self,
        chunks: list[DocumentChunk],
        account: str,
        doc_id: str,
    ) -> None:
        """Ingest all chunks into ChampGraph as episodes."""
        from app.db.champgraph import graph_db, init_graph_db

        init_graph_db()

        for chunk in chunks:
            content = (
                f"Campaign Reference Document: {doc_id}\n"
                f"Section: {chunk.heading}\n"
                f"Content: {chunk.text}"
            )
            try:
                await graph_db._ingest(
                    content=content,
                    name=f"CampaignDoc:{doc_id}:chunk_{chunk.chunk_index}",
                    account_name=account,
                    source=f"campaign_doc_{doc_id}",
                )
            except Exception as e:
                logger.warning(
                    "Failed to ingest chunk %d of %s: %s",
                    chunk.chunk_index, doc_id, e,
                )

    # ── Search / Retrieval ───────────────────────────────────────────────

    def search(
        self,
        query: str,
        max_results: int = 10,
        doc_id_filter: str | None = None,
    ) -> list[DocumentChunk]:
        """Search indexed campaign docs by keyword query."""
        return self.index.search(query, max_results, doc_id_filter)

    def find_relevant_docs(self, campaign_text: str) -> list[str]:
        """
        Given campaign intent/questionnaire text, return doc_ids of
        documents that are relevant. Uses keyword overlap scoring.
        """
        docs = self._repo.load_meta()
        if not docs:
            return []

        query_terms = set(KeywordIndex._extract_terms(campaign_text))
        if not query_terms:
            return []

        scored: list[tuple[str, float]] = []
        for doc_id, meta in docs.items():
            doc_terms = set(KeywordIndex._extract_terms(" ".join(meta.keywords)))
            overlap = len(query_terms & doc_terms)
            if overlap > 0:
                scored.append((doc_id, overlap))

        scored.sort(key=lambda x: x[1], reverse=True)
        return [doc_id for doc_id, _score in scored if _score >= 2]

    def get_context_for_campaign(
        self,
        campaign_text: str,
        max_chunks: int = 8,
    ) -> str:
        """
        Auto-detect relevant campaign docs and return formatted context
        for injection into the AI email generation prompt.
        """
        relevant_docs = self.find_relevant_docs(campaign_text)
        if not relevant_docs:
            return ""

        all_chunks: list[DocumentChunk] = []
        for doc_id in relevant_docs:
            chunks = self.search(campaign_text, max_results=max_chunks, doc_id_filter=doc_id)
            all_chunks.extend(chunks)

        if not all_chunks:
            return ""

        # Deduplicate and limit
        seen = set()
        unique: list[DocumentChunk] = []
        for c in all_chunks:
            key = (c.doc_id, c.chunk_index)
            if key not in seen:
                seen.add(key)
                unique.append(c)

        unique = unique[:max_chunks]

        lines = ["=== CAMPAIGN REFERENCE DOCUMENTS (use for detailed, accurate email content) ==="]
        for chunk in unique:
            lines.append(f"\n--- [{chunk.doc_id}] {chunk.heading} ---")
            lines.append(chunk.text)

        return "\n".join(lines)

    # ── List / Remove ────────────────────────────────────────────────────

    def list_documents(self) -> list[DocumentMeta]:
        """List all ingested campaign documents."""
        docs = self._repo.load_meta()
        return list(docs.values())

    def remove_document(self, doc_id: str) -> bool:
        """Remove a document from the index and metadata store."""
        docs = self._repo.load_meta()
        if doc_id not in docs:
            return False

        # Rebuild index without this doc
        index = self._repo.load_index()
        remaining = [
            c for k, c in index._chunks.items() if k[0] != doc_id
        ]
        new_index = KeywordIndex()
        for c in remaining:
            new_index.add_chunk(c)

        self._repo.save_index(new_index)
        self._repo.remove_doc(doc_id)
        self._index = new_index
        return True

    # ── Helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _extract_top_keywords(text: str, n: int = 20) -> list[str]:
        terms = KeywordIndex._extract_terms(text)
        freq: dict[str, int] = {}
        for t in terms:
            freq[t] = freq.get(t, 0) + 1
        ranked = sorted(freq.items(), key=lambda x: x[1], reverse=True)
        return [term for term, _count in ranked[:n]]


# ─────────────────────────────────────────────────────────────────────────────
# Module-level singleton
# ─────────────────────────────────────────────────────────────────────────────

campaign_docs_service = CampaignDocsService()
