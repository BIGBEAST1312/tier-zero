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
import re
import sys
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
                 refuse_below: float = 4.0):
        self.corpus = corpus
        self.retriever_name = retriever
        self.top_k = top_k
        self.refuse_below = refuse_below
        self.answerer = get_answerer(answerer) if isinstance(answerer, str) else answerer

        texts = [p.search_text for p in corpus.passages]
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
        """Default cut-off is 4.0, chosen from the sweep in scripts/evaluate.py
        on the real knowledge-base articles — and then by judgement.

        On our 47 labelled questions, 4.0 and 4.5 tie on accuracy (93.6%). The
        sweep's tie-break prefers 4.5 because it wrongly answers one fewer
        out-of-scope question. We ship 4.0, because of which questions they are:

            "How do I reset my password?"         scores 4.28
            "Can you reset my password for me?"   scores 4.28

        Identical scores. 4.5 declines both — refusing the single most common
        tier-zero question. 4.0 answers both, and the "for me" request gets the
        self-service reset steps, which is a reasonable reply to it. No cut-off
        can separate the two, because scoring cannot tell asking how to do
        something from asking us to do it. That is the known limitation in
        tests/test_app.py, shown here with real numbers.

        Everything else sits in a clear gap: other out-of-scope questions score
        3.58 or lower, other answerable ones 4.92 or higher.
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
        passages = self.focus(question, r.passages)
        engine = self.answerer.name
        try:
            text = self.answerer.answer(question, passages)
        except Exception as e:
            # Never fail into a fabricated answer. If generation breaks, fall
            # back to extraction, which cannot invent anything.
            #
            # The exception message is the whole diagnostic — it carries the
            # provider's status code and response body — so it goes to the
            # server log in full (the Error log / server log on the host). The
            # student sees a plain sentence: raw provider JSON on a public page
            # looks broken and says nothing they can act on.
            detail = str(e).strip() or "no detail"
            print(f"[answerer:{self.answerer.name}] {type(e).__name__}: {detail}",
                  file=sys.stderr, flush=True)
            text = ("The AI-written answer isn't available right now, so here is "
                    "the matching section of the article.\n\n"
                    + ExtractiveAnswerer().answer(question, passages))
            engine = "extractive (fallback)"
        # Cite what the answer actually used. An extractive answer shows one
        # section, so it cites that one. An LLM answer marks its sources as [1],
        # [2]... against the numbered passages it was given, so cite exactly
        # those — listing every retrieved passage put Wi-Fi articles under a
        # password answer.
        if engine.startswith("extractive"):
            passages = passages[:1]
        else:
            used = []
            for n in re.findall(r"\[(\d+)\]", text):
                i = int(n) - 1
                if 0 <= i < len(passages) and passages[i] not in used:
                    used.append(passages[i])
            passages = used or passages[:1]
        return Answer(text, passages, refused=False, top_score=r.top_score,
                      engine=engine, question=question)

    # Sections that are side notes rather than the procedure itself.
    NOTE_SECTIONS = ("Good to know", "Depending on your situation")

    def focus(self, question: str, passages: list) -> list:
        """Put the best section of the best article first.

        Retrieval is good at choosing the article but poor at choosing the
        section within it: BM25 favours short passages, so a one-line "Good to
        know" note outranks the seven numbered steps the student needs. So keep
        retrieval's choice of article, then pick that article's section with the
        most words in common with the question — preferring the steps over side
        notes on a tie. The other retrieved passages follow, for citations and
        for the LLM answerer's context.
        """
        if not passages:
            return passages
        from .retrieval import tokenize
        page = passages[0].page_id
        q = set(tokenize(question))
        same_page = [p for p in self.corpus.passages if p.page_id == page]

        def rank(p):
            overlap = len(q & set(tokenize(f"{p.section} {p.text}")))
            is_note = p.section in self.NOTE_SECTIONS
            return (-overlap, is_note)

        best = min(same_page, key=rank)
        return [best] + [p for p in passages if p.passage_id != best.passage_id]

    # --- suggestions for the browse view (Epic 5) ---
    def suggestions(self, topic: str = None, n: int = 6) -> list:
        pool = [q for q in SUGGESTED if topic is None or q["topic"] == topic]
        return pool[:n]


SUGGESTED = [
    {"q": "I forgot my NSID password", "topic": "Accounts"},
    {"q": "My new password isn't working on my phone", "topic": "Accounts"},
    {"q": "How do I connect to uofs-secure wifi?", "topic": "Network"},
    {"q": "How do I use the VPN from home?", "topic": "Network"},
    {"q": "How do I set up multi-factor authentication?", "topic": "Security"},
    {"q": "How do I add my USask email to my iPhone?", "topic": "Email"},
    {"q": "How do I install Microsoft Office on my laptop?", "topic": "Microsoft 365"},
    {"q": "How do I activate my Zoom account?", "topic": "Software"},
    {"q": "How do I get SPSS?", "topic": "Software"},
    {"q": "My print job was denied", "topic": "Printing"},
    {"q": "I can't see all my files in Cabinet", "topic": "File storage"},
    {"q": "How do I request a class override?", "topic": "Registration"},
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
