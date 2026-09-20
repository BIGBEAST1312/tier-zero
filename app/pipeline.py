"""The pipeline: retrieve, decide whether to answer, then answer.

The middle step is what most projects skip. Retrieval always returns something —
ask about something the corpus has never heard of and BM25 still hands back its
least-bad passages, and a model given irrelevant passages will still try to be
helpful. That is where invented campus policy comes from.

So retrieval quality is checked before generation runs. The threshold is a real
tradeoff: too high and it refuses questions it could answer, too low and it
answers ones it should not. scripts/evaluate.py sweeps it against labelled
answerable and unanswerable questions instead of leaving it to taste.
"""

import json
import time
from dataclasses import dataclass
from pathlib import Path

from .answering import Answer, ExtractiveAnswerer, get_answerer
from .corpus import Corpus, load_corpus
from .retrieval import BM25, DenseRetriever, reciprocal_rank_fusion

# Escalation, not a dead end. Tier zero exists to hand off cleanly to tier one.
REFUSAL = ("I don't have an article covering that. I can only answer from the IT "
           "knowledge base, and I can't make changes to your account or verify your "
           "identity. For this one, open a ticket with the service desk — include what "
           "you were trying to do, what happened instead, and the exact error message.")


@dataclass
class Retrieved:
    passages: list
    scores: list

    @property
    def top_score(self) -> float:
        return self.scores[0] if self.scores else 0.0


class Bot:
    def __init__(self, corpus: Corpus, retriever: str = "bm25",
                 answerer: str = "extractive", top_k: int = 4,
                 refuse_below: float = 2.0):
        self.corpus = corpus
        self.retriever_name = retriever
        self.top_k = top_k
        self.refuse_below = refuse_below
        self.answerer = get_answerer(answerer) if isinstance(answerer, str) else answerer

        texts = [p.text for p in corpus.passages]
        self.bm25 = self.dense = None
        if retriever in ("bm25", "hybrid"):
            self.bm25 = BM25().fit(texts)
        if retriever in ("dense", "hybrid"):
            self.dense = DenseRetriever().fit(texts)

    @classmethod
    def from_path(cls, path, **kw) -> "Bot":
        return cls(load_corpus(path), **kw)

    def retrieve(self, question: str, k: int = None) -> Retrieved:
        k = k or self.top_k
        if self.retriever_name == "bm25":
            hits = self.bm25.search(question, k)
        elif self.retriever_name == "dense":
            hits = self.dense.search(question, k)
        elif self.retriever_name == "hybrid":
            # Fuse deeper lists than we return, so a passage ranked 6th by one
            # retriever and 2nd by the other can still surface.
            hits = reciprocal_rank_fusion(
                [self.bm25.search(question, k * 3), self.dense.search(question, k * 3)], k)
        else:
            raise KeyError(self.retriever_name)
        return Retrieved([self.corpus.passages[i] for i, _ in hits], [s for _, s in hits])

    def should_refuse(self, r: Retrieved) -> bool:
        """Default cut-off is 2.5, chosen from the sweep in scripts/evaluate.py.

        Cut-offs of 0.5 and 2.5 score the same overall accuracy on our question
        set (95.2%), but they trade differently: 0.5 answers one more real
        question and wrongly answers two out-of-scope ones; 2.5 wrongly answers
        one. We weight a wrong answer as worse than a refusal — a student acts
        on a wrong deadline — so we take 2.5.

        Normalising the score by query length was tried as a second signal and
        did not separate the cases any better (same 95.2% ceiling, degrading
        faster). The remaining leak is documented in tests/test_app.py.
        """
        return not r.passages or r.top_score < self.refuse_below

    def ask(self, question: str) -> Answer:
        question = (question or "").strip()
        if not question:
            return Answer("Ask me an IT support question.", refused=True,
                          engine=self.answerer.name, question=question)
        r = self.retrieve(question)
        if self.should_refuse(r):
            return Answer(REFUSAL, [], refused=True, top_score=r.top_score,
                          engine=self.answerer.name, question=question)
        try:
            text = self.answerer.answer(question, r.passages)
        except Exception as e:
            # Never fail into a fabricated answer. If generation breaks, fall
            # back to extraction, which cannot invent anything.
            text = (f"[{type(e).__name__}] Falling back to extractive answering.\n\n"
                    + ExtractiveAnswerer().answer(question, r.passages))
        return Answer(text, r.passages, refused=False, top_score=r.top_score,
                      engine=self.answerer.name, question=question)

    # --- suggestions for the browse view (Epic 5) ---
    def suggestions(self, topic: str = None, n: int = 6) -> list:
        pool = [q for q in SUGGESTED if topic is None or q["topic"] == topic]
        return pool[:n]


SUGGESTED = [
    {"q": "How do I reset my NSID password?", "topic": "Accounts"},
    {"q": "My account keeps getting locked", "topic": "Accounts"},
    {"q": "How do I connect to eduroam?", "topic": "Network"},
    {"q": "I got a new phone \u2014 how do I move my authenticator?", "topic": "Security"},
    {"q": "Do I need the VPN to check email from home?", "topic": "Network"},
    {"q": "How do I set up email on my phone?", "topic": "Email"},
    {"q": "My assignment upload keeps failing", "topic": "Learning tools"},
    {"q": "I sent a print job but nothing came out", "topic": "Printing"},
    {"q": "What software can I get for free as a student?", "topic": "Software"},
    {"q": "I got a suspicious email about my password", "topic": "Security"},
]


class FeedbackStore:
    """Reports of wrong answers (Epic 2). A flat JSON file is the right amount of
    infrastructure for a few hundred reports."""

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _read(self) -> list:
        if not self.path.exists():
            return []
        try:
            return json.loads(self.path.read_text())
        except json.JSONDecodeError:
            return []

    def add(self, question: str, answer: str, reason: str, citations: list) -> dict:
        rows = self._read()
        row = {
            "id": len(rows) + 1,
            "at": time.strftime("%Y-%m-%d %H:%M"),
            "question": question[:500],
            "answer": answer[:1000],
            "reason": (reason or "").strip()[:500],
            "citations": citations,
            "status": "open",
        }
        rows.append(row)
        self.path.write_text(json.dumps(rows, indent=2))
        return row

    def all(self) -> list:
        return list(reversed(self._read()))

    def open_count(self) -> int:
        return sum(1 for r in self._read() if r.get("status") == "open")
