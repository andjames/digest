"""Fetch and summarize articles asynchronously."""

import asyncio
import json
import os
from datetime import datetime, timedelta

import aiohttp
import feedparser
import yaml
from dateutil import parser as date_parser

from utils import scrape_blog, summarize_article


async def fetch_feed(session: aiohttp.ClientSession, url: str) -> feedparser.FeedParserDict:
    """Retrieve and parse an RSS/Atom feed asynchronously."""
    async with session.get(url) as resp:
        text = await resp.text()
    return feedparser.parse(text)


async def process_rss_source(session: aiohttp.ClientSession, source: dict, cutoff: datetime) -> list:
    """Process a single RSS source and return summary entries."""
    loop = asyncio.get_running_loop()
    feed = await fetch_feed(session, source["url"])
    entries = []
    for entry in feed.entries[:3]:
        published = entry.get("published") or entry.get("updated") or ""
        try:
            pub_date = date_parser.parse(published)
            if pub_date.tzinfo:
                pub_date = pub_date.astimezone(None).replace(tzinfo=None)
        except Exception:
            pub_date = None

        if pub_date and pub_date < cutoff:
            continue

        fallback = getattr(entry, "summary", "") or getattr(entry, "description", "")
        summary = await loop.run_in_executor(None, summarize_article, entry.link, fallback)
        entries.append({
            "source": source["name"],
            "title": entry.title,
            "url": entry.link,
            "published": published,
            "summary": summary,
            "topics": source.get("topics", []),
        })
    return entries


async def process_scrape_source(session: aiohttp.ClientSession, source: dict, cutoff: datetime) -> list:
    """Process a scraped source asynchronously."""
    loop = asyncio.get_running_loop()
    scraped = await loop.run_in_executor(None, scrape_blog, source["url"])
    entries = []
    for entry in scraped[:3]:
        pub_date_str = entry.get("date", "")
        try:
            pub_date = date_parser.parse(pub_date_str)
            if pub_date.tzinfo:
                pub_date = pub_date.astimezone(None).replace(tzinfo=None)
        except Exception:
            pub_date = None

        if pub_date and pub_date < cutoff:
            continue

        summary = await loop.run_in_executor(None, summarize_article, entry["url"], entry.get("summary"))
        entries.append({
            "source": source["name"],
            "title": entry["title"],
            "url": entry["url"],
            "published": pub_date_str,
            "summary": summary,
            "topics": source.get("topics", []),
        })
    return entries


async def main() -> None:
    with open("feeds/sources.yaml") as f:
        sources = yaml.safe_load(f)

    summaries: list = []
    cutoff = datetime.utcnow() - timedelta(days=7)

    async with aiohttp.ClientSession() as session:
        tasks = []
        for source in sources:
            if source["type"] == "rss":
                tasks.append(process_rss_source(session, source, cutoff))
            elif source["type"] == "scrape":
                tasks.append(process_scrape_source(session, source, cutoff))

        results = await asyncio.gather(*tasks)

    for group in results:
        summaries.extend(group)

    os.makedirs("data", exist_ok=True)
    today = datetime.utcnow().strftime("%Y-%m-%d")
    output_file = f"data/summaries_{today}.json"
    with open(output_file, "w") as f:
        json.dump(summaries, f, indent=2)


if __name__ == "__main__":
    asyncio.run(main())

