"""Build data/sources.json from real USask pages.

    # put one URL per line in data/seeds.txt, then:
    python scripts/scrape.py --seeds data/seeds.txt --out data/sources.json

The scraper splits each page on its headings, because heading structure is
already the author's own decision about where one topic ends and the next
begins -- better boundaries than any fixed character count would produce.

Be a good citizen. This checks robots.txt before fetching, sets a real
User-Agent with a contact address, and sleeps between requests. Scrape only
public pages, never anything behind a login, and keep the crawl small. If a
site publishes an API or a data export, use that instead.
"""

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.robotparser
from pathlib import Path

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    sys.exit("pip install requests beautifulsoup4")

USER_AGENT = (
    "CampusInfoBot/0.1 (student project; contact: pcq713@usask.ca)"
)

DROP_TAGS = ["script", "style", "nav", "header", "footer", "aside", "form", "noscript"]
BOILERPLATE = re.compile(
    r"^(skip to|cookie|copyright|all rights reserved|follow us|share this|"
    r"back to top|print this page)", re.I
)


class RobotsCache:
    def __init__(self, respect: bool = True):
        self.respect = respect
        self._cache: dict[str, urllib.robotparser.RobotFileParser] = {}

    def allowed(self, url: str) -> bool:
        if not self.respect:
            return True
        parts = urllib.parse.urlparse(url)
        root = f"{parts.scheme}://{parts.netloc}"
        if root not in self._cache:
            rp = urllib.robotparser.RobotFileParser()
            rp.set_url(f"{root}/robots.txt")
            try:
                rp.read()
            except Exception:
                # Unreachable robots.txt is not permission. Fetch anyway only
                # because the alternative is failing on sites without one, but
                # keep the crawl small and slow.
                pass
            self._cache[root] = rp
        try:
            return self._cache[root].can_fetch(USER_AGENT, url)
        except Exception:
            return True


def clean_text(node) -> str:
    text = node.get_text(" ", strip=True)
    text = re.sub(r"\s+", " ", text)
    return "" if BOILERPLATE.match(text) else text


def extract_sections(html: str) -> tuple[str, list[dict]]:
    """Split a page into (title, [{heading, text}]) using h1-h3 boundaries."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(DROP_TAGS):
        tag.decompose()

    title = ""
    if soup.title and soup.title.string:
        title = re.sub(r"\s+", " ", soup.title.string).strip()
    h1 = soup.find("h1")
    if h1:
        title = clean_text(h1) or title

    main = soup.find("main") or soup.find("article") or soup.body or soup
    sections, heading, buf = [], "", []

    def flush():
        body = "\n\n".join(p for p in buf if p)
        if len(body) > 80:
            sections.append({"heading": heading, "text": body})

    for el in main.find_all(["h1", "h2", "h3", "p", "li"]):
        if el.name in ("h1", "h2", "h3"):
            flush()
            heading = clean_text(el)
            buf = []
        else:
            t = clean_text(el)
            if len(t) > 40:
                buf.append(t)
    flush()
    return title, sections


def slugify(url: str) -> str:
    path = urllib.parse.urlparse(url).path.strip("/")
    slug = re.sub(r"[^a-z0-9]+", "-", path.lower()).strip("-")
    return slug[-60:] or "index"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="data/seeds.txt")
    ap.add_argument("--out", default="data/sources.json")
    ap.add_argument("--topic", default="Other", help="topic label for this batch")
    ap.add_argument("--delay", type=float, default=1.5, help="seconds between requests")
    ap.add_argument("--timeout", type=float, default=20.0)
    ap.add_argument("--ignore-robots", action="store_true")
    args = ap.parse_args()

    seed_path = Path(args.seeds)
    if not seed_path.exists():
        sys.exit(f"no seed file at {seed_path}. Put one URL per line there first.")

    urls = [ln.strip() for ln in seed_path.read_text().splitlines()
            if ln.strip() and not ln.startswith("#")]
    if not urls:
        sys.exit("seed file is empty")

    robots = RobotsCache(respect=not args.ignore_robots)
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT

    docs, skipped = [], 0
    for i, url in enumerate(urls, 1):
        if not robots.allowed(url):
            print(f"  [{i}/{len(urls)}] robots.txt disallows {url}")
            skipped += 1
            continue
        try:
            resp = session.get(url, timeout=args.timeout)
            resp.raise_for_status()
        except Exception as e:
            print(f"  [{i}/{len(urls)}] failed {url}: {e}")
            skipped += 1
            continue

        title, sections = extract_sections(resp.text)
        if not sections:
            print(f"  [{i}/{len(urls)}] no usable content at {url}")
            skipped += 1
            continue

        docs.append({
            "page_id": slugify(url),
            "title": title or slugify(url),
            "url": url,
            "topic": args.topic,
            "fetched": time.strftime("%Y-%m-%d"),
            "synthetic": False,
            "sections": sections,
        })
        words = sum(len(s["text"].split()) for s in sections)
        print(f"  [{i}/{len(urls)}] {title[:50]!r} — {len(sections)} sections, {words} words")
        time.sleep(args.delay)

    if not docs:
        sys.exit("nothing scraped; check your seed URLs")

    Path(args.out).write_text(json.dumps(docs, indent=2))
    print(f"\nwrote {len(docs)} documents to {args.out} ({skipped} skipped)")
    print("Now rebuild your eval set \u2014 data/eval_questions.json refers to the "
          "old page ids and will be wrong.")


if __name__ == "__main__":
    main()
