"""Turning retrieved passages into an answer.

Hard requirement: every claim traces to a retrieved passage. Invented instructions
about MFA or account recovery are worse than no answer — they can lock someone out
entirely, which turns a self-service question into a desk visit.

Two answerers, deliberately separate so a bad answer can be blamed on the right
half of the system:

  ExtractiveAnswerer  - no API key, no network. Selects sentences from the
    retrieved passages. Cannot hallucinate because it never writes anything; it
    also reads stiffly. If its answer is wrong, retrieval is at fault.
  ClaudeAnswerer      - calls the Anthropic API with the passages as context and
    a system prompt that forbids outside knowledge.
"""

import os
import re
from dataclasses import dataclass, field

SYSTEM_PROMPT = """\
You are a tier-zero IT support assistant for the University of Saskatchewan. You \
answer using ONLY the numbered knowledge base articles provided.

Rules:
- Use only information stated in the sources. Never add outside knowledge, even \
if you are confident it is correct.
- Cite the source number in square brackets after each claim, like [1] or [2].
- If the articles do not answer the question, say so plainly and tell the person to \
open a ticket with the service desk. Do not guess.
- You cannot reset passwords, unlock accounts, verify identity or change anything on \
an account. If asked to, say so and direct the person to the service desk.
- Never invent or repeat credentials, and never ask for a password.
- If the sources only partly answer it, say which part you can answer and which \
you cannot.
- Be concise and practical. Two or three sentences is usually enough.
- Never invent specific settings, server names, URLs, phone numbers or timeframes. \
If a specific detail is not in the articles, say it is not listed. Wrong instructions \
about an account can lock someone out entirely.
"""


@dataclass
class Answer:
    text: str
    passages: list = field(default_factory=list)
    refused: bool = False
    top_score: float = 0.0
    engine: str = ""
    question: str = ""

    def citations(self) -> list:
        if self.refused:
            return []
        seen, out = set(), []
        for p in self.passages:
            c = p.citation()
            if c["label"] in seen:
                continue
            seen.add(c["label"])
            out.append(c)
        return out

    def to_dict(self) -> dict:
        return {
            "text": self.text, "refused": self.refused,
            "top_score": round(self.top_score, 2), "engine": self.engine,
            "citations": self.citations(), "question": self.question,
        }


def build_context(passages: list) -> str:
    return "\n\n".join(
        f"[{i}] {p.page_title} — {p.section}\n{p.text}" for i, p in enumerate(passages, 1)
    )


class ExtractiveAnswerer:
    """Returns the best-matching section of one article, word for word.

    No generation, so it cannot fabricate — its ceiling is retrieval quality.

    It used to pick the individual sentences that overlapped most with the
    question, from any of the retrieved passages. On a knowledge base made of
    numbered procedures that was the wrong design: it pulled step 1 from one
    article and step 4 from another, out of order, and read like one answer when
    it was three. A procedure is only useful whole and in order, so this returns
    the top-ranked passage intact. Mixing articles is the LLM answerer's job,
    because it can say which article each part came from.
    """

    name = "extractive"

    def answer(self, question: str, passages: list, max_sentences: int = 3) -> str:
        if not passages:
            return ""
        return passages[0].text


class ClaudeAnswerer:
    """Anthropic API. Needs ANTHROPIC_API_KEY and `pip install anthropic`."""

    name = "claude"

    # Haiku is the right tier here: the model is writing two or three sentences
    # from passages we already retrieved, not reasoning. It costs about a fifth
    # of Sonnet and answers faster, which matters more on a support page.
    # Override with TZ_MODEL if you want to compare.
    def __init__(self, model: str = None, max_tokens: int = 400):
        model = model or os.environ.get("TZ_MODEL", "claude-haiku-4-5-20251001")
        self.model, self.max_tokens = model, max_tokens
        self._client = None

    def _client_or_raise(self):
        if self._client is None:
            try:
                import anthropic
            except ImportError as e:
                raise ImportError("pip install anthropic") from e
            if not os.environ.get("ANTHROPIC_API_KEY"):
                raise RuntimeError("set ANTHROPIC_API_KEY in your environment")
            self._client = anthropic.Anthropic()
        return self._client

    def answer(self, question: str, passages: list) -> str:
        client = self._client_or_raise()
        msg = client.messages.create(
            model=self.model, max_tokens=self.max_tokens, system=SYSTEM_PROMPT,
            messages=[{"role": "user",
                       "content": f"Sources:\n\n{build_context(passages)}\n\nQuestion: {question}"}],
        )
        return "".join(b.text for b in msg.content if b.type == "text").strip()


class OpenAICompatAnswerer:
    """One adapter for every provider that speaks the OpenAI chat format.

    Groq, OpenRouter, Google Gemini's compatibility endpoint and a local Ollama
    all accept the same request shape, so switching provider is two environment
    variables rather than another class. Uses `requests`, which is already a
    dependency, so there is no SDK to install per provider.

        TZ_LLM_BASE_URL   e.g. https://api.groq.com/openai/v1
        TZ_LLM_MODEL      the provider's model name
        TZ_LLM_API_KEY    omit entirely for a local Ollama

    Free options that work with this, checked September 2026 — verify the
    current limits yourself, free tiers change often:

      Ollama (local, no key, no account, works offline)
        TZ_LLM_BASE_URL=http://localhost:11434/v1
        TZ_LLM_MODEL=llama3.2:3b

      Groq (free tier, very fast)
        TZ_LLM_BASE_URL=https://api.groq.com/openai/v1
        TZ_LLM_MODEL=llama-3.3-70b-versatile

      OpenRouter (has models with a :free suffix)
        TZ_LLM_BASE_URL=https://openrouter.ai/api/v1
        TZ_LLM_MODEL=meta-llama/llama-3.3-70b-instruct:free

      Google Gemini (official OpenAI-compatible endpoint; key from
      aistudio.google.com, not a Vertex AI service account)
        TZ_LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai
        TZ_LLM_MODEL=gemini-2.5-flash

        Free tier is roughly 15 requests/minute and 1,500/day on Flash, which is
        comfortably above our own rate limit. Note that Google's free tier terms
        have historically allowed prompts to be used for product improvement \u2014
        worth knowing for a product pitched at an IT department, and worth
        stating in the deliverable. Our prompts contain public KB text and the
        question asked, never account data.

    The grounding prompt is the same one Claude gets. A smaller model follows it
    less reliably — expect it to occasionally answer something it should have
    escalated. That is worth measuring rather than assuming: run
    scripts/evaluate.py and compare.
    """

    name = "openai-compat"

    def __init__(self, base_url: str = None, model: str = None, api_key: str = None,
                 max_tokens: int = 400, timeout: int = 30):
        self.base_url = (base_url or os.environ.get("TZ_LLM_BASE_URL", "")).rstrip("/")
        self.model = model or os.environ.get("TZ_LLM_MODEL", "")
        self.api_key = api_key if api_key is not None else os.environ.get("TZ_LLM_API_KEY", "")
        self.max_tokens = max_tokens
        self.timeout = timeout

    def answer(self, question: str, passages: list) -> str:
        if not self.base_url or not self.model:
            raise RuntimeError(
                "set TZ_LLM_BASE_URL and TZ_LLM_MODEL (see OpenAICompatAnswerer "
                "for working examples)"
            )
        try:
            import requests
        except ImportError as e:
            raise ImportError("pip install requests") from e

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        resp = requests.post(
            f"{self.base_url}/chat/completions",
            headers=headers,
            timeout=self.timeout,
            json={
                "model": self.model,
                "max_tokens": self.max_tokens,
                "temperature": 0.2,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user",
                     "content": f"Sources:\n\n{build_context(passages)}\n\n"
                                f"Question: {question}"},
                ],
            },
        )
        if resp.status_code != 200:
            raise RuntimeError(f"{self.model} returned {resp.status_code}: "
                               f"{resp.text[:200]}")
        data = resp.json()
        try:
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError) as e:
            raise RuntimeError(f"unexpected response shape: {str(data)[:200]}") from e


def get_answerer(name: str):
    if name == "claude":
        return ClaudeAnswerer()
    if name == "local":
        return OpenAICompatAnswerer()
    if name == "extractive":
        return ExtractiveAnswerer()
    raise KeyError(f"unknown answerer {name!r}; "
                   f"use 'extractive', 'claude' or 'local'")
