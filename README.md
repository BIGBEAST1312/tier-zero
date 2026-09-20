# Tier Zero

A tier-zero IT support assistant for the University of Saskatchewan. Ask about
accounts, wireless, VPN, email, learning tools, printing, software or security,
and get an answer taken from the IT knowledge base with a link to the article —
and a clean escalation to the service desk when there is no article for it.

**Team 8 — We'll Study It Later** · Aarya, Mohit, Hetank, Haryan, Priyesh

---

## Why "Tier Zero"

In IT support, tier zero is the self-service layer: the knowledge base and search
that resolve a problem before it becomes a tier-one ticket. That is exactly what
this is, and the name carries the business case. Escalation to tier one is part of
the concept rather than a failure of it — which is why the product is designed to
hand off rather than guess.

## Run it

```bash
pip install -r requirements.txt
python run.py                 # http://127.0.0.1:5000
python tests/test_app.py      # 18 tests
python scripts/evaluate.py    # metrics → /maintainer/quality
```

No API key, no model download and no network needed for any of that.

Optional:

```bash
pip install sentence-transformers      # then: python run.py --retriever hybrid
pip install anthropic                  # then: ANTHROPIC_API_KEY=... python run.py --answerer claude
```

## What's here

```
app/
  corpus.py       KB article / passage model, chunking, topic coverage
  retrieval.py    BM25, optional dense embeddings, rank fusion
  answering.py    extractive and Claude answerers, grounding prompt, citations
  pipeline.py     retrieve → decide whether to answer → answer; feedback store
  server.py       Flask routes
templates/ static/   the interface, mobile-first
site/                3D scroll-driven landing page (no CDN; three.js vendored)
scripts/
  add_page.py     add a KB article by pasting its text
  scrape.py       collect articles from the public KB
  ingest.py       merge a scraped batch
  evaluate.py     recall@k, MRR, escalation threshold sweep
tests/test_app.py
data/
  sources.json        the knowledge base — PLACEHOLDER CONTENT, see below
  eval_questions.json 46 labelled questions, 10 of them out of scope
```

## What it will not do

Stated plainly because a service owner will ask first:

- It cannot reset a password, unlock an account, or change anything on an account
- It cannot verify identity
- It only reads public knowledge base articles — never tickets, never account data
- Anything requiring action or verification is escalated to the service desk

## The data in here is fake

`data/sources.json` is **placeholder content written for development**, not the
real USask IT knowledge base. Every article is flagged `"synthetic": true` and the
interface shows a sample-data banner because of it. Replace it before the numbers
mean anything:

```bash
python scripts/add_page.py                        # paste an article
python scripts/scrape.py --seeds data/seeds/accounts.txt --topic Accounts --out data/new.json
python scripts/ingest.py data/new.json
```

Then rewrite `data/eval_questions.json` against the real articles.

## Measurements

From `python scripts/evaluate.py` on the placeholder corpus with BM25:

| Metric | Value |
|---|---|
| recall@5 | 94.4% |
| MRR | 0.836 |
| Escalation accuracy | 87.0% at the chosen cut-off |

### Why the cut-off is 2.0

Cut-offs of 0.5 through 2.0 all score 87.0%, but they trade differently. At 0.5 the
product answers every real question and wrongly answers six it should have
escalated; at 2.0 it wrongly answers five and declines one it could have handled. A
wrong instruction about an account can lock someone out — which turns a
self-service question into a desk visit, the opposite of what tier zero is for. So
we take the higher cut-off.

## Known limitations

- **Scoring cannot tell a question from a request.** "How do I reset my password"
  and "Can you reset my password for me" retrieve the same article with nearly the
  same score, because they share every distinctive word. One is ours to answer and
  one is not. No threshold separates them; only something that reads the request
  can. `ClaudeAnswerer`'s system prompt instructs the model to catch this, but the
  pipeline does not yet enforce it, and the extractive answerer cannot.
  `tests/test_app.py::test_action_requests_are_escalated_not_answered` asserts the
  gap so it cannot change unnoticed.
- **Near-miss questions from other domains still leak.** "When is the tuition
  payment deadline" clears the score gate because "payment" appears in the phishing
  article. Same root cause as above.
- **BM25 misses on vocabulary mismatch.** A question phrased entirely differently
  from the article wording scores low. That is what `--retriever hybrid` is for.
- **No conversation memory.** Each question is independent.
- **Chunk size is unvalidated.** 700 characters with 120 of overlap was chosen, not
  measured.
- **Retrieval is measured; answer correctness is not.** recall@5 says the right
  article was found, not that the answer was right.
- **One shared password on `/maintainer`, not user accounts.** Set
  `TZ_MAINTAINER_PASSWORD` and `TZ_SECRET_KEY` before hosting. There is no
  per-person audit trail and no password reset.
- **Development server only.** Do not expose `run.py` to the internet.

## Free alternatives to the Claude API

`--answerer local` speaks the OpenAI chat format, which Groq, OpenRouter, Google
Gemini and a local Ollama all accept. Switching provider is two environment
variables, not a code change.

**Ollama — completely free, no account, works offline.** Best for development.
Install from ollama.com, then:

```bash
ollama pull llama3.2:3b
TZ_LLM_BASE_URL=http://localhost:11434/v1 TZ_LLM_MODEL=llama3.2:3b \
  python run.py --answerer local
```

It cannot be hosted on a free tier — Render's free plan has nowhere near the RAM.

**Google Gemini — what we use.** Free tier, generous limits, works when hosted.
Get a key at aistudio.google.com, then:

```bash
TZ_LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai \\
TZ_LLM_MODEL=gemini-2.5-flash \\
TZ_LLM_API_KEY=your-key \\
  python run.py --answerer local
```

Free tier is around 15 requests/minute and 1,500/day on Flash — above our own
rate limit, so ours binds first. One thing to state in the deliverable: Google's
free tier terms have historically allowed prompts to be used for product
improvement. Our prompts contain public knowledge base text and the question
asked, never account data, but a service owner will ask and the honest answer is
better than a surprised one.

**Groq or OpenRouter** also work with the same adapter. Values are in the
docstring of `OpenAICompatAnswerer`. Free tiers change often; check current
limits before relying on one for a demo.

Endpoint and limits checked September 2026 against
<https://ai.google.dev/gemini-api/docs/openai>.

**What you give up.** Smaller models follow the grounding prompt less reliably —
expect more cases where it answers something it should have escalated. Don't
assume that; measure it. Run `scripts/evaluate.py` against each provider and put
the comparison in the deliverable. "We compared three models on our own question
set" is a considerably better sentence than "we used Claude."

## Cost, and who pays

The API key lives on the server, not in visitors' browsers. Nobody using the site
needs a key — which also means **we pay for every question anyone asks.**

Each question sends roughly 1,100 tokens in (four retrieved passages plus the
system prompt) and gets about 150 back. On Haiku 4.5 at $1/$5 per million tokens
that is around **$0.002 per question**, so a thousand questions costs about two
dollars. Haiku is the default because the model is writing two or three sentences
from passages we already retrieved, not reasoning — Sonnet costs roughly five
times as much for no visible gain here. Override with `TZ_MODEL` to compare.

Three things protect the credit balance:

- **Rate limiting** on `/api/ask` — 12 questions per minute and 120 per hour per
  IP by default. Tune with `TZ_ASK_PER_MINUTE` and `TZ_ASK_PER_HOUR`.
- **A spend limit in the Anthropic console.** Set one before hosting. The rate
  limit is per process and resets on restart; a hard spend cap does not.
- **The extractive answerer**, which costs nothing. If the credit runs out
  mid-demo, `--answerer extractive` still works.

Pricing checked September 2026 against
<https://platform.claude.com/docs/en/about-claude/pricing>. Verify before quoting
it in a deliverable.

## AI use disclosure

Members of the team used AI assistants while building this project, as permitted by
the course. AI-generated code is marked in-line with the tool, the reviewing team
member and the date. See `docs/ai-usage.md`.

## Not an official service

A student project reading public knowledge base articles. Not an official
University of Saskatchewan service and not endorsed by ICT. It cannot change
anything on your account. For account access, identity verification or anything
urgent, contact the service desk.
