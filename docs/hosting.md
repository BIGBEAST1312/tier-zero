# Hosting Tier Zero

## Read this first

**Don't put the placeholder corpus on a public URL.** Right now the app will
confidently tell a stranger how account recovery works, using content that
was written for development. The sample-data banner helps, but a public site
answering USask IT questions is a different thing from a local demo. Either host it
privately for the team and TA, or wait until real scraped pages are in.

**Lock the service-owner views before hosting.** Set `TZ_MAINTAINER_PASSWORD` and
`/maintainer` requires a sign-in. Also set `TZ_SECRET_KEY` to a long random string,
or sessions will not survive a restart and will fail across multiple workers. Set
`TZ_HTTPS=1` so the session cookie is only sent over HTTPS.

It is one shared password, not user accounts — no per-person audit trail and no
reset. Describe it that way rather than implying the views are properly protected.

**Do you actually need hosting?** For the course, a portfolio site on GitLab Pages
plus a local demo at the walkthrough may be all that's required. Ask Palash before
spending time on it.

---

## Why GitLab Pages won't work for the app

GitLab Pages serves static files only. Flask needs a running Python process, so
the app cannot live there. Use Pages for the **portfolio site** (your deliverable
documents) and host the **app** somewhere that runs Python.

---

## Option 1 — PythonAnywhere (easiest, free)

Best fit for a student Flask project. Always on, no cold starts, no card needed.

1. Sign up at pythonanywhere.com — free "Beginner" account
2. **Consoles → Bash**, then:
   ```bash
   git clone https://git.cs.usask.ca/<your-group>/tier-zero.git
   cd tier-zero
   mkvirtualenv --python=/usr/bin/python3.10 tierzero
   pip install -r requirements.txt
   ```
3. **Web → Add a new web app → Manual configuration → Python 3.10**
4. Set **Source code** to `/home/<you>/tier-zero`
5. Set **Virtualenv** to `/home/<you>/.virtualenvs/tierzero`
6. Edit the WSGI configuration file it gives you; replace the contents with:
   ```python
   import sys, os
   path = '/home/<you>/tier-zero'
   if path not in sys.path:
       sys.path.insert(0, path)
   os.environ['TZ_MAINTAINER_PASSWORD'] = '<pick something long>'
   os.environ['TZ_SECRET_KEY'] = '<a long random string>'
   os.environ['TZ_HTTPS'] = '1'
   from wsgi import app as application
   ```
7. **Reload**. You get `<you>.pythonanywhere.com`.

To update after a push: Bash console, `git pull`, then hit Reload.

**Free tier limits:** one web app, a CPU-seconds quota, and outbound internet is
restricted to a whitelist — which matters if you later use the Claude answerer.
BM25 and extractive answers work fine.

---

## Option 2 — Render (free, git-connected)

Auto-deploys on every push, which is nicer for a five-person team.

1. Push the repo to GitHub (Render doesn't connect to a private departmental
   GitLab). Keep GitLab as the graded repo and mirror to GitHub for deployment.
2. render.com → **New → Web Service** → connect the repo
3. It reads `render.yaml`, so the build and start commands are already set
4. Add `TZ_MAINTAINER_PASSWORD`, `TZ_SECRET_KEY` and `TZ_HTTPS=1` under Environment

**The catch:** the free tier spins down after 15 minutes idle, and the next
request takes 30–60 seconds to wake it. Fine for a shared link, bad for a live
demo — open the page a minute before you present.

---

## Option 3 — Ask the department

Before signing up for anything, ask Palash or the CS systems staff whether the
department hosts student project apps. Some do, and it avoids the third-party
question entirely. One email, and it may be the simplest answer.

---

## Running it yourself for a demo

For the product walkthrough, the most reliable option is your own laptop:

```bash
pip install -r requirements.txt
python run.py --port 5055
```

No network dependency, no cold start, nothing to go wrong in front of a marker.
Have this working as a fallback even if you do host it.

---

## Before you deploy anywhere

- [ ] Real scraped pages in `data/sources.json`, or accept that it is a demo
- [ ] `TZ_MAINTAINER_PASSWORD`, `TZ_SECRET_KEY` and `TZ_HTTPS` set
- [ ] `python tests/test_app.py` passes
- [ ] The footer disclaimer is intact — "not affiliated with or endorsed by the
      University of Saskatchewan"
- [ ] `ANTHROPIC_API_KEY` is in the host's environment settings, never committed
- [ ] A spend limit set in the Anthropic console — the endpoint is public and
      every question costs money
- [ ] Rate limits checked (`TZ_ASK_PER_MINUTE`, `TZ_ASK_PER_HOUR`)
- [ ] Someone other than you has opened the URL and it worked

## What breaks when you host it

**Feedback reports don't persist on Render.** `data/feedback.json` lives on the
container's disk, which is wiped on every deploy and every spin-down. Reports
survive locally and on PythonAnywhere. If you need them durable on an ephemeral
host, that is the point where a real database becomes justified — and until then
it is not.

**Never run `run.py` as the public server.** It is Flask's development server:
single-threaded, no request limits. `Procfile` and `render.yaml` use gunicorn,
which is the right thing. On Windows use `waitress-serve --port=8000 wsgi:app`
instead, since gunicorn doesn't run there.
