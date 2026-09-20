"""Production entry point.

Gunicorn and most hosts look for a module-level `app`. Configuration comes from
environment variables so the same image runs locally and on a host.

    TZ_RETRIEVER   bm25 | dense | hybrid        (default bm25)
    TZ_ANSWERER    extractive | claude          (default extractive)
    TZ_THRESHOLD   refusal cut-off              (default 2.5)
    TZ_MAINTAINER_PASSWORD  if set, /maintainer requires a sign-in
    TZ_SECRET_KEY           signs the session cookie; required in production
    TZ_HTTPS                set to 1 so the session cookie is HTTPS-only
    TZ_MODEL                which Claude model to use (default: Haiku 4.5)
    TZ_ASK_PER_MINUTE       public question limit per IP (default 12)
    TZ_ASK_PER_HOUR         public question limit per IP (default 120)

Run locally with:  gunicorn wsgi:app        (or: waitress-serve --port=8000 wsgi:app)
"""

import os

from app.server import create_app

app = create_app(
    retriever=os.environ.get("TZ_RETRIEVER", "bm25"),
    answerer=os.environ.get("TZ_ANSWERER", "extractive"),
    refuse_below=float(os.environ.get("TZ_THRESHOLD", "2.0")),
)
