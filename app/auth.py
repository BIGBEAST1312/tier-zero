"""Access control for the service-owner views.

What this is: a single shared password, checked against an environment variable,
held in a signed session cookie. Enough to keep KB coverage and reported answers
off a public URL.

What this is not: user accounts. There is one password for everyone who needs
access, no per-person audit trail, and no password reset. Say that plainly in the
deliverable rather than implying the views are properly protected — a service
owner who sees an honest description will trust the rest of the system more.

Configuration:

    TZ_MAINTAINER_PASSWORD   set it and the views require sign-in
                             unset and they stay open, which is fine locally
    TZ_SECRET_KEY            signs the session cookie; set it in production
"""

import hmac
import os
import secrets
import time
from functools import wraps

from flask import (abort, current_app, redirect, render_template, request,
                   session, url_for)

SESSION_KEY = "tz_maintainer"
# Deliberately coarse: a shared password can't be brute-forced quickly if each
# process only allows a handful of attempts per window.
MAX_ATTEMPTS = 5
WINDOW_SECONDS = 300

_attempts: dict[str, list[float]] = {}


def configure(app):
    """Attach the secret key and return whether a password is required."""
    password = os.environ.get("TZ_MAINTAINER_PASSWORD", "")

    secret = os.environ.get("TZ_SECRET_KEY")
    if not secret:
        # A random key per process means sessions do not survive a restart and
        # break entirely across multiple workers. Fine locally, wrong in
        # production, so it warns rather than failing silently.
        secret = secrets.token_hex(32)
        if password:
            app.logger.warning(
                "TZ_SECRET_KEY is not set, so a random one was generated. "
                "Sign-ins will not survive a restart and will fail across "
                "multiple workers. Set TZ_SECRET_KEY before deploying."
            )
    app.secret_key = secret

    app.config.update(
        MAINTAINER_PASSWORD=password,
        SESSION_COOKIE_HTTPONLY=True,      # not readable from JavaScript
        SESSION_COOKIE_SAMESITE="Lax",     # not sent on cross-site POSTs
        SESSION_COOKIE_SECURE=bool(os.environ.get("TZ_HTTPS")),
    )
    return bool(password)


def _throttled(ip: str) -> bool:
    now = time.time()
    tries = [t for t in _attempts.get(ip, []) if now - t < WINDOW_SECONDS]
    _attempts[ip] = tries
    return len(tries) >= MAX_ATTEMPTS


def _record_attempt(ip: str):
    _attempts.setdefault(ip, []).append(time.time())


def is_signed_in() -> bool:
    if not current_app.config.get("MAINTAINER_PASSWORD"):
        return True                       # no password configured, no gate
    return session.get(SESSION_KEY) is True


def maintainer_only(view):
    """Redirect to the sign-in page rather than 404ing, so a service owner who
    bookmarked the page gets somewhere useful."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not is_signed_in():
            return redirect(url_for("maintainer_login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def register(app, base_context):
    @app.get("/maintainer/login")
    def maintainer_login():
        if is_signed_in():
            return redirect(request.args.get("next") or url_for("maintainer"))
        return render_template("login.html", error=None,
                               next=request.args.get("next", ""), **base_context())

    @app.post("/maintainer/login")
    def maintainer_login_post():
        ip = request.remote_addr or "unknown"
        if _throttled(ip):
            return render_template(
                "login.html", next=request.form.get("next", ""),
                error="Too many attempts. Wait a few minutes and try again.",
                **base_context()), 429

        expected = current_app.config.get("MAINTAINER_PASSWORD", "")
        given = request.form.get("password", "")
        # compare_digest rather than == so the comparison time doesn't leak how
        # much of the password was correct.
        if expected and hmac.compare_digest(given, expected):
            session.clear()
            session[SESSION_KEY] = True
            session.permanent = False     # ends when the browser closes
            dest = request.form.get("next") or url_for("maintainer")
            # Only ever redirect within this site.
            if not dest.startswith("/") or dest.startswith("//"):
                dest = url_for("maintainer")
            return redirect(dest)

        _record_attempt(ip)
        return render_template("login.html", next=request.form.get("next", ""),
                               error="That password is not right.",
                               **base_context()), 401

    @app.post("/maintainer/logout")
    def maintainer_logout():
        session.clear()
        return redirect(url_for("home"))
