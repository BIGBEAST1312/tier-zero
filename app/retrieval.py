"""Retrieval.

BM25 is the baseline and the only retriever needed to ship. It scores a passage
by how many query terms it contains, weighting rare terms higher and penalising
long passages so they are not rewarded just for length.

Where it wins: exact names. A query containing "U-Pass" matches the passage
containing "U-Pass" with certainty.

Where it loses: vocabulary mismatch. "Where can I work out" shares no words with
"fitness centre", so BM25 scores it at nothing. That is the gap DenseRetriever
fills, and why hybrid usually beats either alone. Dense is optional because it
needs a model download.
"""

import math
import re
from collections import Counter

STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being", "am",
    "do", "does", "did", "doing", "have", "has", "had", "having", "i", "me",
    "my", "we", "our", "you", "your", "it", "its", "they", "them", "their",
    "this", "that", "these", "those", "and", "or", "but", "if", "of", "at",
    "by", "for", "with", "about", "to", "from", "in", "on", "as", "can",
    "could", "would", "should", "will", "there", "here", "what", "when",
    "where", "which", "who", "how", "why", "get", "got", "any", "some",
}

# Hyphenated and apostrophed terms stay whole: splitting "U-Pass" turns one rare,
# highly specific token into two common ones and destroys the match.
TOKEN_RE = re.compile(r"[a-z0-9]+(?:[-'][a-z0-9]+)*")


def tokenize(text: str, drop_stopwords: bool = True) -> list:
    toks = TOKEN_RE.findall(text.lower())
    return [t for t in toks if t not in STOPWORDS] if drop_stopwords else toks


class BM25:
    """Okapi BM25.

    k1 controls how quickly term frequency saturates — a word appearing ten
    times is not ten times as relevant as once. b controls the document length
    penalty; b=0 disables length normalisation entirely.
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.docs, self.tf = [], []
        self.idf, self.avg_len = {}, 0.0

    def fit(self, texts: list) -> "BM25":
        self.docs = [tokenize(t) for t in texts]
        self.tf = [Counter(d) for d in self.docs]
        df = Counter()
        for c in self.tf:
            df.update(c.keys())
        n = max(len(self.docs), 1)
        # Smoothed IDF: never negative, unlike the textbook form which goes
        # negative for terms in more than half the collection.
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}
        self.avg_len = sum(len(d) for d in self.docs) / n
        return self

    def search(self, query: str, k: int = 5) -> list:
        q_terms = tokenize(query)
        scores = []
        for i, tf in enumerate(self.tf):
            if not tf:
                scores.append(0.0)
                continue
            dl = len(self.docs[i])
            norm = self.k1 * (1 - self.b + self.b * dl / max(self.avg_len, 1e-9))
            s = 0.0
            for term in q_terms:
                f = tf.get(term)
                if f:
                    s += self.idf.get(term, 0.0) * (f * (self.k1 + 1)) / (f + norm)
            scores.append(s)
        ranked = sorted(enumerate(scores), key=lambda x: -x[1])
        return [(i, s) for i, s in ranked[:k] if s > 0]


class DenseRetriever:
    """Embedding retrieval. Optional — needs `pip install sentence-transformers`
    and a one-time ~90MB model download."""

    DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

    def __init__(self, model_name: str = DEFAULT_MODEL):
        self.model_name = model_name
        self._model = None
        self.matrix = None

    def _load(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as e:
                raise ImportError(
                    "Dense retrieval needs sentence-transformers:\n"
                    "    pip install sentence-transformers\n"
                    "Until then the app runs fine on BM25."
                ) from e
            self._model = SentenceTransformer(self.model_name)
        return self._model

    @staticmethod
    def _norm(m):
        import numpy as np
        return m / np.clip(np.linalg.norm(m, axis=1, keepdims=True), 1e-9, None)

    def fit(self, texts: list) -> "DenseRetriever":
        import numpy as np
        emb = self._load().encode(texts, batch_size=32, show_progress_bar=False)
        self.matrix = self._norm(np.asarray(emb, dtype="float32"))
        return self

    def search(self, query: str, k: int = 5) -> list:
        import numpy as np
        q = np.asarray(self._load().encode([query]), dtype="float32")
        scores = (self.matrix @ self._norm(q)[0]).tolist()
        order = np.argsort(scores)[::-1][:k]
        return [(int(i), float(scores[i])) for i in order]


def reciprocal_rank_fusion(rankings: list, k: int = 5, damping: int = 60) -> list:
    """Combine rankings by position, not by score.

    BM25 scores are unbounded and cosine similarities sit in [-1, 1], so adding
    them directly lets BM25 dominate on magnitude alone. RRF uses rank only, so
    it needs no calibration.
    """
    fused = {}
    for ranking in rankings:
        for rank, (idx, _) in enumerate(ranking):
            fused[idx] = fused.get(idx, 0.0) + 1.0 / (damping + rank + 1)
    return sorted(fused.items(), key=lambda x: -x[1])[:k]
