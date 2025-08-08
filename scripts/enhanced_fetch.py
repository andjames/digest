"""Enhanced asynchronous article fetching and processing."""

import asyncio
import glob
import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import partial
from typing import Dict, List, Optional, Set

import aiohttp
import feedparser
import yaml
from dateutil import parser as date_parser

from enhanced_utils import (
    detect_duplicate_content,
    enhanced_summarize_article,
    extract_breaking_news_indicators,
    get_article_content,
    score_article_relevance,
    score_article_sentiment,
)

@dataclass
class Article:
    source: str
    title: str
    url: str
    published: str
    published_dt: Optional[datetime]
    summary: str
    topics: List[str]
    content_hash: str
    relevance_score: float
    sentiment_score: float
    is_breaking: bool
    
def load_existing_articles() -> Set[str]:
    """Load existing article hashes from prior digests to avoid duplicates."""
    hashes: Set[str] = set()
    for path in glob.glob("data/summaries_*.json"):
        try:
            with open(path, "r") as f:
                existing = json.load(f)
                if isinstance(existing, dict):
                    existing = existing.get("articles", existing)

                hashes.update({
                    article.get("content_hash", "")
                    for article in existing
                    if isinstance(article, dict) and article.get("content_hash")
                })
        except (FileNotFoundError, json.JSONDecodeError):
            continue
    return hashes

def is_recent_article(published_date: str, hours_threshold: int = 24 * 7) -> bool:
    """Check if article was published within the threshold hours."""
    try:
        pub_date = parse_published_date(published_date)
        if not pub_date:
            return True

        threshold = datetime.now().astimezone() - timedelta(hours=hours_threshold)
        return pub_date >= threshold
    except Exception:
        return True  # If parsing fails, include the article

def parse_published_date(published_date: str) -> Optional[datetime]:
    """Parse a published date string into a ``datetime`` object."""
    if not published_date:
        return None
    try:
        pub_date = date_parser.parse(published_date.strip())
        if pub_date.tzinfo is None:
            pub_date = pub_date.replace(tzinfo=datetime.now().astimezone().tzinfo)
        else:
            pub_date = pub_date.astimezone(datetime.now().astimezone().tzinfo)
        return pub_date
    except Exception:
        return None

def create_content_hash(title: str, url: str) -> str:
    """Create a hash for duplicate detection."""
    content = f"{title.lower().strip()}{url}"
    return hashlib.md5(content.encode()).hexdigest()

def enhance_source_metadata(source: Dict) -> Dict:
    """Add enhanced metadata to sources."""
    enhancements = {
        "priority": source.get("priority", "medium"),  # high, medium, low
        "update_frequency": source.get("update_frequency", "daily"),  # hourly, daily, weekly
        "content_type": source.get("content_type", "general"),  # breaking, research, analysis
        "relevance_keywords": source.get("relevance_keywords", []),
        "max_articles": source.get("max_articles", 5)
    }
    return {**source, **enhancements}

async def fetch_feed(session: aiohttp.ClientSession, url: str) -> feedparser.FeedParserDict:
    """Fetch and parse an RSS/Atom feed asynchronously."""
    async with session.get(url) as resp:
        text = await resp.text()
    return feedparser.parse(text)


async def _process_source(
    session: aiohttp.ClientSession,
    source: Dict,
    existing_hashes: Set[str],
) -> List[Article]:
    """Fetch and process a single source."""
    loop = asyncio.get_running_loop()
    articles: List[Article] = []

    source = enhance_source_metadata(source)

    try:
        if source["type"] == "rss":
            feed = await fetch_feed(session, source["url"])

            # Get more articles for high-priority sources
            max_articles = source["max_articles"]
            if source.get("priority") == "high":
                max_articles *= 2

            for entry in feed.entries[:max_articles]:
                published = entry.get("published") or entry.get("updated") or ""
                if not is_recent_article(published, hours_threshold=24 * 7):
                    continue

                content_hash = create_content_hash(entry.title, entry.link)
                if content_hash in existing_hashes:
                    continue

                article_content = await loop.run_in_executor(
                    None, get_article_content, entry.link
                )

                is_breaking = extract_breaking_news_indicators(
                    entry.title,
                    article_content,
                    source.get("relevance_keywords", []),
                )

                relevance_score = score_article_relevance(
                    entry.title,
                    article_content,
                    source.get("topics", []),
                    source.get("relevance_keywords", []),
                )

                if relevance_score < 0.3 and not is_breaking:
                    continue

                fallback = getattr(entry, "summary", "") or getattr(entry, "description", "")
                sentiment_score = score_article_sentiment(article_content or fallback)
                summarize = partial(
                    enhanced_summarize_article,
                    entry.link,
                    article_content or fallback,
                    is_breaking=is_breaking,
                    relevance_score=relevance_score,
                )
                summary = await loop.run_in_executor(None, summarize)

                article = Article(
                    source=source["name"],
                    title=entry.title,
                    url=entry.link,
                    published=published,
                    published_dt=parse_published_date(published),
                    summary=summary,
                    topics=source.get("topics", []),
                    content_hash=content_hash,
                    relevance_score=relevance_score,
                    sentiment_score=sentiment_score,
                    is_breaking=is_breaking,
                )

                articles.append(article)
                existing_hashes.add(content_hash)

    except Exception as e:
        print(f"Error processing source {source['name']}: {e}")

    return articles


async def fetch_enhanced_articles(
    config_path: str = "feeds/enhanced_sources.yaml",
) -> List[Article]:
    """Enhanced article fetching with smart filtering and deduplication."""

    with open(config_path) as f:
        sources = yaml.safe_load(f)

    existing_hashes = load_existing_articles()

    # Prioritize high-priority sources for breaking news
    sources.sort(
        key=lambda x: {"high": 0, "medium": 1, "low": 2}.get(x.get("priority", "medium"), 1)
    )

    async with aiohttp.ClientSession() as session:
        tasks = [
            _process_source(session, src, existing_hashes) for src in sources
        ]
        results = await asyncio.gather(*tasks)

    articles = [article for group in results for article in group]

    articles.sort(
        key=lambda x: (
            not x.is_breaking,
            -x.relevance_score,
            x.published_dt or datetime.min,
        ),
        reverse=False,
    )

    return articles

async def main() -> None:
    """Main asynchronous execution function."""
    articles = await fetch_enhanced_articles()

    duplicate_urls = detect_duplicate_content(
        [{"title": a.title, "url": a.url} for a in articles]
    )
    if duplicate_urls:
        articles = [a for a in articles if a.url not in duplicate_urls]

    summaries = []
    for article in articles:
        summary_data = {
            "source": article.source,
            "title": article.title,
            "url": article.url,
            "published": article.published,
            "summary": article.summary,
            "topics": article.topics,
            "content_hash": article.content_hash,
            "relevance_score": round(article.relevance_score, 2),
            "sentiment_score": round(article.sentiment_score, 2),
            "is_breaking": article.is_breaking,
        }
        summaries.append(summary_data)

    summaries = summaries[:50]

    output = {
        "generated_at": datetime.now().isoformat(),
        "total_articles": len(summaries),
        "breaking_news_count": sum(1 for s in summaries if s["is_breaking"]),
        "articles": summaries,
    }

    os.makedirs("data", exist_ok=True)
    today = datetime.utcnow().strftime("%Y-%m-%d")
    output_file = f"data/summaries_{today}.json"
    with open(output_file, "w") as f:
        json.dump(output, f, indent=2)

    print(f"✅ Processed {len(summaries)} articles ({output['breaking_news_count']} breaking)")


if __name__ == "__main__":
    asyncio.run(main())

