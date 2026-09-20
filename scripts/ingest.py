"""Merge a freshly scraped batch into data/sources.json.

    python scripts/scrape.py --seeds data/housing.txt --topic Housing --out data/new.json
    python scripts/ingest.py data/new.json

Pages are matched on page_id: an existing page is replaced (a refresh), a new one
is appended. Nothing is deleted, so a bad scrape never silently empties the
knowledge base.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "data" / "sources.json"


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: python scripts/ingest.py <scraped.json>")
    incoming = json.loads(Path(sys.argv[1]).read_text())
    existing = json.loads(TARGET.read_text()) if TARGET.exists() else []

    by_id = {p["page_id"]: p for p in existing}
    added = refreshed = 0
    for page in incoming:
        if page["page_id"] in by_id:
            refreshed += 1
        else:
            added += 1
        by_id[page["page_id"]] = page

    merged = list(by_id.values())
    TARGET.write_text(json.dumps(merged, indent=2))
    synthetic = sum(1 for p in merged if p.get("synthetic"))
    print(f"{added} added, {refreshed} refreshed. {len(merged)} pages total.")
    if synthetic:
        print(f"WARNING: {synthetic} pages are still placeholder content.")


if __name__ == "__main__":
    main()
