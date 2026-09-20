# Seed lists

One file per topic. Each line is a knowledge base article URL to scrape; lines
starting with # are ignored.

    python scripts/scrape.py --seeds data/seeds/accounts.txt --topic Accounts --out data/new.json
    python scripts/ingest.py data/new.json

## Check robots.txt first

Read the robots.txt of whichever host serves the IT knowledge base before
scraping anything. `scripts/scrape.py` checks automatically and skips disallowed
URLs, but you should know the rules rather than letting the script discover them.

## Ask before you scrape

This project has a named stakeholder in IT support. Ask them whether they would
rather you scraped the public knowledge base or were given an export. An export is
cleaner, avoids load on their systems, and the conversation builds the
relationship the deliverables depend on.

## Never use ticket data

Real tickets contain personal information. Use public knowledge base articles as
the corpus. Informal observation from working at the desk is fine as context for
requirements — say so, and say where the line is.

## Scale

Aim for 40–60 articles. Start with whatever the survey says generates the most
repeat questions, not with what we assume.
