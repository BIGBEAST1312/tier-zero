"""The knowledge base: source pages, and the passages we cut them into.

Entities here match the conceptual data model in the deliverable:
SourcePage has many Passages; Topic groups SourcePages.

Chunk size is the first real design decision. Too small and an answer is split
across two passages that may not both be retrieved; too large and the answer is
buried among unrelated text. There is no correct value, so scripts/evaluate.py
measures it rather than us guessing.
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Passage:
    passage_id: str
    page_id: str
    page_title: str
    url: str
    section: str
    text: str
    topic: str = ""
    synthetic: bool = False

    def citation(self) -> dict:
        label = f"{self.page_title} — {self.section}" if self.section else self.page_title
        return {"label": label, "url": self.url, "page_id": self.page_id}


@dataclass
class SourcePage:
    page_id: str
    title: str
    url: str
    topic: str
    fetched: str = ""
    synthetic: bool = False
    sections: list = field(default_factory=list)


@dataclass
class Corpus:
    pages: list = field(default_factory=list)
    passages: list = field(default_factory=list)

    def __len__(self):
        return len(self.passages)

    @property
    def has_synthetic(self) -> bool:
        return any(p.synthetic for p in self.pages)

    def topics(self) -> dict:
        """Topic -> list of pages, for the browse view (Epic 5)."""
        out = {}
        for page in self.pages:
            out.setdefault(page.topic or "Other", []).append(page)
        return dict(sorted(out.items()))

    def coverage(self) -> list:
        """Per-topic counts, for the maintainer view (Epic 3)."""
        rows = []
        for topic, pages in self.topics().items():
            n_passages = sum(1 for p in self.passages if p.topic == topic)
            words = sum(len(p.text.split()) for p in self.passages if p.topic == topic)
            rows.append({
                "topic": topic,
                "pages": len(pages),
                "passages": n_passages,
                "words": words,
                "thin": n_passages < 4,
            })
        return sorted(rows, key=lambda r: r["passages"])

    def page(self, page_id: str):
        return next((p for p in self.pages if p.page_id == page_id), None)


def split_paragraphs(text: str) -> list:
    parts = re.split(r"\n\s*\n", text.strip())
    return [re.sub(r"\s+", " ", p).strip() for p in parts if p.strip()]


def chunk_section(text: str, target_chars: int = 700, overlap_chars: int = 120) -> list:
    """Pack paragraphs up to target_chars, carrying a tail of the previous chunk
    so a sentence spanning the boundary is not lost. Paragraph boundaries are
    respected rather than cutting at a fixed count — a passage that begins
    mid-sentence retrieves badly."""
    paras = split_paragraphs(text)
    chunks, cur = [], ""
    for p in paras:
        if cur and len(cur) + len(p) + 1 > target_chars:
            chunks.append(cur)
            cur = (cur[-overlap_chars:] + " " + p).strip() if overlap_chars else p
        else:
            cur = f"{cur} {p}".strip()
    if cur:
        chunks.append(cur)
    return chunks


def load_corpus(path, target_chars: int = 700, overlap_chars: int = 120) -> Corpus:
    raw = json.loads(Path(path).read_text())
    corpus = Corpus()
    for doc in raw:
        page = SourcePage(
            page_id=doc["page_id"], title=doc["title"], url=doc.get("url", ""),
            topic=doc.get("topic", "Other"), fetched=doc.get("fetched", ""),
            synthetic=bool(doc.get("synthetic", False)),
            sections=doc.get("sections", []),
        )
        corpus.pages.append(page)
        for s_i, section in enumerate(page.sections):
            for c_i, text in enumerate(chunk_section(section["text"], target_chars, overlap_chars)):
                corpus.passages.append(Passage(
                    passage_id=f"{page.page_id}#{s_i}.{c_i}",
                    page_id=page.page_id, page_title=page.title, url=page.url,
                    section=section.get("heading", ""), text=text,
                    topic=page.topic, synthetic=page.synthetic,
                ))
    return corpus
