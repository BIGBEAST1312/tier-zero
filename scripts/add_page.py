"""Add one page to the knowledge base by pasting its text.

    python scripts/add_page.py

Scraping is repeatable, but for a page or two by hand this is faster and gives
cleaner text — you drop the navigation junk as you paste instead of filtering it
out afterwards. Both are legitimate; say in the deliverable which you used.

Existing pages are matched on page_id and replaced, so running this again on the
same URL is how you refresh a page rather than duplicate it.
"""

import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "data" / "sources.json"

TOPICS = ["Accounts", "Network", "Security", "Email", "Microsoft 365",
          "Software", "File storage", "Printing", "Registration", "Devices"]


def slugify(url: str) -> str:
    path = re.sub(r"^https?://", "", url).strip("/")
    slug = re.sub(r"[^a-z0-9]+", "-", path.lower()).strip("-")
    return slug[-60:] or "page"


def ask(prompt: str, default: str = "") -> str:
    hint = f" [{default}]" if default else ""
    got = input(f"{prompt}{hint}: ").strip()
    return got or default


def read_block(prompt: str) -> str:
    """Read a multi-line paste, ending on a line containing only END."""
    print(f"{prompt}\n  (paste the text, then a line containing only END)")
    lines = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line.strip() == "END":
            break
        lines.append(line)
    return "\n".join(lines).strip()


def clean(text: str) -> str:
    """Collapse the single newlines a browser copy leaves behind, but keep the
    blank lines between paragraphs — the chunker splits on those, and losing
    them turns a whole section into one unsplittable passage."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    paras = re.split(r"\n\s*\n", text)
    out = []
    for p in paras:
        p = re.sub(r"\s*\n\s*", " ", p).strip()
        p = re.sub(r"[ \t]{2,}", " ", p)
        if len(p) > 30:                      # drop stray nav fragments
            out.append(p)
    return "\n\n".join(out)


def main():
    print("Add a page to the knowledge base. Ctrl-C to stop.\n")

    url = ask("Page URL")
    if not url.startswith(("http://", "https://")):
        sys.exit("URL must start with http:// or https://")

    title = ask("Page title")
    if not title:
        sys.exit("a title is required — it shows in every citation")

    print(f"\nTopics: {', '.join(TOPICS)}")
    topic = ask("Topic", "Other")

    page_id = ask("Page id", slugify(url))

    sections = []
    while True:
        print(f"\n--- Section {len(sections) + 1} ---")
        heading = ask("Section heading (blank to finish)")
        if not heading:
            break
        body = clean(read_block("Section text"))
        if not body:
            print("  nothing usable in that paste, skipping")
            continue
        paras = body.count("\n\n") + 1
        print(f"  kept {len(body.split())} words in {paras} paragraph(s)")
        if paras == 1 and len(body.split()) > 180:
            print("  WARNING: one long paragraph. If the original had paragraph")
            print("  breaks, keep the blank lines — retrieval works much better.")
        sections.append({"heading": heading, "text": body})

    if not sections:
        sys.exit("no sections captured, nothing written")

    page = {
        "page_id": page_id, "title": title, "url": url, "topic": topic,
        "fetched": time.strftime("%Y-%m-%d"), "synthetic": False,
        "sections": sections,
    }

    existing = json.loads(TARGET.read_text()) if TARGET.exists() else []
    by_id = {p["page_id"]: p for p in existing}
    action = "refreshed" if page_id in by_id else "added"
    by_id[page_id] = page

    merged = list(by_id.values())
    TARGET.write_text(json.dumps(merged, indent=2))

    words = sum(len(s["text"].split()) for s in sections)
    print(f"\n{action} '{title}' — {len(sections)} sections, {words} words")
    print(f"{len(merged)} pages in the knowledge base")

    left = sum(1 for p in merged if p.get("synthetic"))
    if left:
        print(f"{left} placeholder pages remain. The sample-data banner stays "
              f"until they are all replaced or removed.")
    else:
        print("No placeholder pages left — the sample-data banner is gone.")

    print("\nNext: restart the app and ask it something about this page.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nstopped, nothing written")
