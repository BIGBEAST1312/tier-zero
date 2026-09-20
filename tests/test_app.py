"""Tests for the pieces that break quietly.

The dangerous failures here still produce a plausible-looking answer: a chunker
that drops text, a retriever that returns nothing, a refusal threshold that never
fires. None of these raise an exception, so they have to be asserted.

Each test names the epic it covers, so the deliverable can point at them.

    python tests/test_app.py        (or: python -m pytest tests/ -v)
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.corpus import chunk_section, load_corpus          # noqa: E402
from app.retrieval import BM25, tokenize                   # noqa: E402
from app.pipeline import Bot, FeedbackStore                # noqa: E402
from app.server import create_app                          # noqa: E402

SOURCES = ROOT / "data" / "sources.json"
QUESTIONS = ROOT / "data" / "eval_questions.json"


# ----------------------------------------------------------- corpus / chunking
def test_tokenizer_keeps_hyphenated_terms():
    """'U-Pass' must survive as one token. Splitting it turns a rare, highly
    specific term into two common ones and destroys the match."""
    toks = tokenize("What is the U-Pass and can I opt out?")
    assert "u-pass" in toks
    assert "the" not in toks and "is" not in toks


def test_chunker_loses_no_content():
    text = "\n\n".join(f"Paragraph number {i} with enough words to matter." for i in range(12))
    joined = " ".join(chunk_section(text, target_chars=200, overlap_chars=0))
    for i in range(12):
        assert f"Paragraph number {i} " in joined, f"lost paragraph {i}"


def test_corpus_loads_with_topics_and_metadata():
    c = load_corpus(SOURCES)
    assert len(c) > 10
    assert len(c.pages) >= 10
    for p in c.passages:
        assert p.page_id and p.page_title and p.text and p.topic
    assert len(c.topics()) >= 5


def test_coverage_flags_thin_topics():
    """Epic 3 — the maintainer needs to see what to scrape next."""
    rows = load_corpus(SOURCES).coverage()
    assert rows
    assert all({"topic", "pages", "passages", "thin"} <= set(r) for r in rows)
    assert rows == sorted(rows, key=lambda r: r["passages"]), "thinnest topic should sort first"


# ---------------------------------------------------------------- retrieval
def test_bm25_ranks_exact_term_first():
    bm = BM25().fit([
        "The recreation centre has a weight room and a swimming pool.",
        "Residence rooms include a bed frame, desk and chair.",
        "Group study rooms can be booked online in advance.",
    ])
    assert bm.search("swimming pool", k=1)[0][0] == 0


def test_bm25_returns_nothing_for_unrelated_query():
    """No match must mean an empty list, not a low-scoring wrong answer. The
    refusal gate depends on this."""
    bm = BM25().fit(["The recreation centre has a weight room."])
    assert bm.search("quantum chromodynamics", k=3) == []


def test_retrieval_recall_is_reasonable():
    """A regression guard, not a target. If a change drops recall below this,
    something broke."""
    bot = Bot.from_path(SOURCES, top_k=5)
    qs = [q for q in json.loads(QUESTIONS.read_text()) if q["expected_page"]]
    hits = sum(q["expected_page"] in [p.page_id for p in bot.retrieve(q["question"], k=5).passages]
               for q in qs)
    assert hits / len(qs) >= 0.70, f"recall@5 fell to {hits / len(qs):.1%}"


# ------------------------------------------------------- Epic 1 + 2: answering
def test_answer_carries_citations():
    """Epic 2 — an answer without a KB article behind it is not shippable."""
    bot = Bot.from_path(SOURCES)
    a = bot.ask("How do I reset my NSID password?")
    assert not a.refused
    assert a.citations(), "an answer must carry sources"
    assert "kb-20" in [p.page_id for p in a.passages]


def test_answer_text_comes_only_from_retrieved_passages():
    """The property that makes the extractive answerer hallucination-proof."""
    bot = Bot.from_path(SOURCES)
    a = bot.ask("How do I connect to uofs-secure wifi?")
    haystack = " ".join(p.text for p in a.passages)
    for sentence in a.text.split(". "):
        s = sentence.strip().rstrip(".")
        if len(s) > 20:
            assert s in haystack, f"unsourced text: {s[:60]!r}"


def test_refuses_clearly_out_of_domain_questions():
    bot = Bot.from_path(SOURCES)
    for q in ["What is the capital of Australia?",
              "Who is the CIO of the university?",
              "Has the university had a data breach?"]:
        assert bot.ask(q).refused, f"should have declined: {q!r}"


def test_refusal_carries_no_citations():
    """A refusal must not cite anything — citations imply an answer."""
    bot = Bot.from_path(SOURCES)
    a = bot.ask("What is the capital of Australia?")
    assert a.refused and a.citations() == []


def test_action_requests_are_escalated_not_answered():
    """Tier zero can retrieve and explain. It cannot do anything to an account.

    'Can you reset my password for me?' retrieves the password article strongly,
    because it shares every important word with it. Scoring alone cannot tell
    the difference between asking how to do something and asking us to do it,
    so this is the case the ClaudeAnswerer system prompt has to catch. The
    extractive answerer cannot, and that is worth knowing rather than hiding.
    """
    bot = Bot.from_path(SOURCES)
    answered = [q for q in ["Can you reset my password for me?",
                            "Unlock my account right now",
                            "Can you give me someone else's email address?"]
                if not bot.ask(q).refused]
    assert answered, ("retrieval-only escalation improved \u2014 update this test "
                      "to assert the new behaviour")


# ------------------------------------------------------------- Epic 2: reports
def test_feedback_round_trip(tmp_path=None):
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        store = FeedbackStore(Path(d) / "fb.json")
        assert store.all() == []
        row = store.add("q?", "a.", "wrong deadline", [{"label": "X", "url": ""}])
        assert row["id"] == 1 and row["status"] == "open"
        assert store.open_count() == 1
        store.add("q2?", "a2.", "", [])
        assert len(store.all()) == 2
        assert store.all()[0]["id"] == 2, "newest report should come first"


# ------------------------------------------------------------- maintainer lock
def _locked_client(password="letmein"):
    """A client with the maintainer password configured, restored afterwards."""
    import os
    os.environ["TZ_MAINTAINER_PASSWORD"] = password
    os.environ["TZ_SECRET_KEY"] = "test-key-not-a-real-secret"
    try:
        return create_app().test_client()
    finally:
        pass


def _unset_password():
    import os
    os.environ.pop("TZ_MAINTAINER_PASSWORD", None)
    os.environ.pop("TZ_SECRET_KEY", None)


def test_maintainer_open_when_no_password_configured():
    """Locally, with nothing configured, the views stay open. Convenience is the
    right default for a course project; hosting is where the lock matters."""
    _unset_password()
    c = create_app().test_client()
    assert c.get("/maintainer").status_code == 200


def test_maintainer_redirects_to_login_when_locked():
    c = _locked_client()
    try:
        r = c.get("/maintainer")
        assert r.status_code == 302
        assert "/maintainer/login" in r.headers["Location"]
        assert c.get("/maintainer/quality").status_code == 302
    finally:
        _unset_password()


def test_wrong_password_is_rejected():
    c = _locked_client()
    try:
        r = c.post("/maintainer/login", data={"password": "wrong"})
        assert r.status_code == 401
        assert c.get("/maintainer").status_code == 302, "still locked after a bad try"
    finally:
        _unset_password()


def test_correct_password_grants_access_then_logout_revokes_it():
    c = _locked_client()
    try:
        r = c.post("/maintainer/login", data={"password": "letmein"})
        assert r.status_code == 302
        assert c.get("/maintainer").status_code == 200, "should be signed in"
        c.post("/maintainer/logout")
        assert c.get("/maintainer").status_code == 302, "logout should revoke access"
    finally:
        _unset_password()


def test_login_redirect_stays_on_this_site():
    """An open redirect would let someone send a sign-in link that bounces the
    service owner to another site afterwards."""
    c = _locked_client()
    try:
        r = c.post("/maintainer/login",
                   data={"password": "letmein", "next": "https://evil.example/x"})
        assert r.headers["Location"].endswith("/maintainer")
        r = c.post("/maintainer/login",
                   data={"password": "letmein", "next": "//evil.example/x"})
        assert "evil.example" not in r.headers["Location"]
    finally:
        _unset_password()


def test_public_pages_stay_open_when_maintainer_is_locked():
    """Locking the service-owner views must not lock out students."""
    c = _locked_client()
    try:
        for path in ["/", "/browse", "/healthz"]:
            assert c.get(path).status_code == 200, path
        r = c.post("/api/ask", json={"question": "how do I connect to uofs-secure wifi"})
        assert r.status_code == 200 and r.get_json()["citations"]
    finally:
        _unset_password()


def test_repeated_wrong_passwords_are_throttled():
    from app import auth
    auth._attempts.clear()
    c = _locked_client()
    try:
        codes = [c.post("/maintainer/login", data={"password": "no"}).status_code
                 for _ in range(auth.MAX_ATTEMPTS + 1)]
        assert 429 in codes, "brute force should be throttled"
    finally:
        auth._attempts.clear()
        _unset_password()


# ----------------------------------------------------------------- web routes
def test_every_page_renders():
    app = create_app()
    client = app.test_client()
    for path in ["/", "/browse", "/maintainer", "/maintainer/quality", "/healthz"]:
        assert client.get(path).status_code == 200, f"{path} did not render"


def test_ask_endpoint_returns_citations():
    client = create_app().test_client()
    r = client.post("/api/ask", json={"question": "how do I connect to uofs-secure wifi"})
    data = r.get_json()
    assert r.status_code == 200
    assert data["refused"] is False
    assert data["citations"], "answer must carry citations"


def test_ask_endpoint_refuses_out_of_scope():
    client = create_app().test_client()
    data = client.post("/api/ask", json={"question": "capital of Australia"}).get_json()
    assert data["refused"] is True and data["citations"] == []


def test_ask_endpoint_is_rate_limited():
    """The ask endpoint is public and each call to the Claude answerer costs
    money. Without a limit one loop drains the API credit."""
    import os
    os.environ["TZ_ASK_PER_MINUTE"] = "3"
    try:
        c = create_app().test_client()
        codes = [c.post("/api/ask", json={"question": "uofs-secure wifi"}).status_code
                 for _ in range(5)]
        assert 429 in codes, "repeated questions should be throttled"
        assert codes[0] == 200, "the first few must still work"
    finally:
        os.environ.pop("TZ_ASK_PER_MINUTE", None)


def test_local_answerer_resolves_and_fails_clearly_when_unconfigured():
    """The free-provider adapter must give a usable error rather than a stack
    trace when the environment variables are missing."""
    from app.answering import get_answerer
    import os
    for var in ("TZ_LLM_BASE_URL", "TZ_LLM_MODEL"):
        os.environ.pop(var, None)
    a = get_answerer("local")
    assert a.name == "openai-compat"
    try:
        a.answer("anything", [])
        assert False, "should have raised"
    except RuntimeError as e:
        assert "TZ_LLM_BASE_URL" in str(e)


def test_unknown_answerer_name_is_rejected():
    from app.answering import get_answerer
    try:
        get_answerer("gpt5")
        assert False, "should have raised"
    except KeyError as e:
        assert "extractive" in str(e), "the error should list the valid options"


def test_empty_question_is_handled():
    client = create_app().test_client()
    assert client.post("/api/ask", json={"question": "   "}).status_code == 200


def test_topic_page_renders_for_every_topic():
    """Epic 5 — every topic on the browse page must open."""
    app = create_app()
    client = app.test_client()
    for topic in app.config["BOT"].corpus.topics():
        assert client.get(f"/topic/{topic}").status_code == 200, topic


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {t.__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
