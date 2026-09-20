"""Run the Tier Zero web app.

    python run.py                       # BM25 retrieval, extractive answers
    python run.py --answerer claude     # needs ANTHROPIC_API_KEY
    python run.py --retriever hybrid    # needs sentence-transformers
    python run.py --password hunter2    # lock /maintainer behind a password
    python run.py --answerer local      # Ollama, Groq, OpenRouter or Gemini
                                        # (set TZ_LLM_BASE_URL and TZ_LLM_MODEL)

Development server only. Do not expose it to the internet.
"""

import argparse
import os
import secrets

from app.server import create_app

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--retriever", default="bm25", choices=["bm25", "dense", "hybrid"])
    ap.add_argument("--answerer", default="extractive", choices=["extractive", "claude", "local"])
    ap.add_argument("--threshold", type=float, default=4.0,
                    help="refuse to answer below this retrieval score")
    ap.add_argument("--password", default=None,
                    help="lock the service-owner views behind this password")
    ap.add_argument("--port", type=int, default=5000)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()

    if args.password:
        os.environ["TZ_MAINTAINER_PASSWORD"] = args.password
        os.environ.setdefault("TZ_SECRET_KEY", secrets.token_hex(32))

    app = create_app(retriever=args.retriever, answerer=args.answerer,
                     refuse_below=args.threshold)
    print(f"http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=False)
