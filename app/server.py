"""Flask app.

Routes map onto the five epics:

  Epic 1 Ask and Answer      /            /api/ask
  Epic 2 Trust               citations rendered with every answer, /api/report
  Epic 3 Knowledge Base      /maintainer  /maintainer/coverage
  Epic 4 Quality             /maintainer/quality
  Epic 5 Discover            /browse      /topic/<topic>

Development server only — no auth on the maintainer views, which is fine for a
course project but should be stated plainly rather than left implied.
"""

import json
import os
import time
from collections import defaultdict
from pathlib import Path

from flask import Flask, jsonify, render_template, request

from . import auth

from .corpus import load_corpus
from .pipeline import SUGGESTED, Bot, FeedbackStore

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def create_app(retriever: str = "bm25", answerer: str = "extractive",
               refuse_below: float = 4.0) -> Flask:
    app = Flask(__name__,
                template_folder=str(ROOT / "templates"),
                static_folder=str(ROOT / "static"))

    corpus = load_corpus(DATA / "sources.json")
    bot = Bot(corpus, retriever=retriever, answerer=answerer, refuse_below=refuse_below)
    feedback = FeedbackStore(DATA / "feedback.json")

    app.config["BOT"] = bot
    app.config["FEEDBACK"] = feedback

    # Sign-in for the service-owner views. See app/auth.py for what this does
    # and does not protect.
    locked = auth.configure(app)
    app.config["MAINTAINER_LOCKED"] = locked

    def base():
        """Context every page needs. The sidebar counts come straight from the
        loaded corpus — never hard-coded, so the interface can't claim a scale
        the knowledge base doesn't have."""
        return {
            "n_passages": len(corpus),
            "n_pages": len(corpus.pages),
            "synthetic": corpus.has_synthetic,
            "retriever": bot.retriever_name,
            "sidebar_topics": sorted(corpus.coverage(),
                                     key=lambda r: -r["passages"]),
            "maintainer_locked": locked,
            "signed_in": auth.is_signed_in(),
        }

    auth.register(app, base)

    # ---------------------------------------------- Epic 1 + 2: ask and trust
    @app.get("/")
    def home():
        return render_template("index.html", suggestions=SUGGESTED[:4], **base())

    # Every question hitting the Claude answerer costs money, and this endpoint
    # is public. Without a limit, one person with a loop empties the API credit
    # and the demo dies. Per-IP and per-hour, held in memory: fine for a single
    # process, and the right amount of infrastructure for a course project.
    # Also set a spend limit in the Anthropic console — belt and braces.
    ASK_PER_MINUTE = int(os.environ.get("TZ_ASK_PER_MINUTE", "12"))
    ASK_PER_HOUR = int(os.environ.get("TZ_ASK_PER_HOUR", "120"))
    _asks = defaultdict(list)

    def over_limit(ip: str) -> bool:
        now = time.time()
        hits = [t for t in _asks[ip] if now - t < 3600]
        _asks[ip] = hits
        if len(hits) >= ASK_PER_HOUR:
            return True
        if len([t for t in hits if now - t < 60]) >= ASK_PER_MINUTE:
            return True
        hits.append(now)
        return False

    @app.post("/api/ask")
    def api_ask():
        ip = request.remote_addr or "unknown"
        if over_limit(ip):
            return jsonify({
                "text": ("You're asking faster than this can keep up with. "
                         "Give it a minute and try again."),
                "refused": True, "top_score": 0.0, "engine": "rate-limit",
                "citations": [], "question": "",
            }), 429
        payload = request.get_json(silent=True) or {}
        answer = bot.ask(payload.get("question", ""))
        return jsonify(answer.to_dict())

    @app.post("/api/report")
    def api_report():
        payload = request.get_json(silent=True) or {}
        if not payload.get("question"):
            return jsonify({"error": "nothing to report"}), 400
        row = feedback.add(
            question=payload.get("question", ""),
            answer=payload.get("answer", ""),
            reason=payload.get("reason", ""),
            citations=payload.get("citations", []),
        )
        return jsonify({"ok": True, "id": row["id"]})

    # ------------------------------------------------------ Epic 5: discover
    @app.get("/browse")
    def browse():
        return render_template("browse.html", topics=corpus.topics(),
                               suggestions=SUGGESTED, **base())

    @app.get("/topic/<topic>")
    def topic(topic):
        pages = corpus.topics().get(topic, [])
        qs = [s for s in SUGGESTED if s["topic"] == topic]
        return render_template("topic.html", topic=topic, pages=pages,
                               suggestions=qs, **base())

    # ------------------------------------------- Epic 3 + 4: maintainer views
    @app.get("/maintainer")
    @auth.maintainer_only
    def maintainer():
        return render_template("maintainer.html",
                               coverage=corpus.coverage(),
                               reports=feedback.all()[:20],
                               open_reports=feedback.open_count(),
                               pages=corpus.pages, **base())

    @app.get("/maintainer/quality")
    @auth.maintainer_only
    def quality():
        path = ROOT / "data" / "eval_results.json"
        results = json.loads(path.read_text()) if path.exists() else None
        return render_template("quality.html", results=results, **base())

    @app.get("/landing")
    def landing():
        """The 3D marketing page. Served from site/ so the same files can also be
        published straight to GitLab Pages as the project portfolio front page."""
        from flask import send_from_directory
        return send_from_directory(ROOT / "site", "index.html")

    @app.get("/landing/vendor/<path:name>")
    def landing_vendor(name):
        from flask import send_from_directory
        return send_from_directory(ROOT / "site" / "vendor", name)

    @app.get("/healthz")
    def healthz():
        return jsonify({"ok": True, "passages": len(corpus)})

    return app
