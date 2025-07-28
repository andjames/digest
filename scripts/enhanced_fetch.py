import feedparser
import yaml
import json
import os
import argparse
from datetime import datetime, timedelta
from typing import List, Dict, Set
import hashlib
from dataclasses import dataclass
from enhanced_utils import (
    enhanced_summarize_article, 
    get_article_content, 
    detect_duplicate_content,
    score_article_relevance,
    extract_breaking_news_indicators
)

@dataclass
class Article:
    source: str
    title: str
    url: str
    published: str
    summary: str
    topics: List[str]
    content_hash: str
    relevance_score: float
    is_breaking: bool
    
def load_existing_articles() -> Set[str]:
    """Load existing article hashes to avoid duplicates."""
    try:
        with open("data/summaries.json", "r") as f:
            existing = json.load(f)
            return {article.get("content_hash", "") for article in existing if article.get("content_hash")}
    except (FileNotFoundError, json.JSONDecodeError):
        return set()

def is_recent_article(published_date: str, hours_threshold: int = 48) -> bool:
    """Check if article was published within the threshold hours."""
    try:
        # Parse various date formats
        for fmt in ["%a, %d %b %Y %H:%M:%S %Z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S"]:
            try:
                pub_date = datetime.strptime(published_date.strip(), fmt)
                if pub_date.tzinfo is None:
                    pub_date = pub_date.replace(tzinfo=datetime.now().astimezone().tzinfo)
                break
            except ValueError:
                continue
        else:
            return True  # If we can't parse, include it
        
        threshold = datetime.now().astimezone() - timedelta(hours=hours_threshold)
        return pub_date >= threshold
    except Exception:
        return True  # If parsing fails, include the article

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

def fetch_enhanced_articles(config_path: str = "feeds/enhanced_sources.yaml") -> List[Article]:
    """Enhanced article fetching with smart filtering and deduplication.

    Parameters
    ----------
    config_path: str
        Path to YAML configuration file describing the news sources.
    """

    with open(config_path) as f:
        sources = yaml.safe_load(f)
    
    existing_hashes = load_existing_articles()
    articles = []
    
    # Prioritize high-priority sources for breaking news
    sources.sort(key=lambda x: {"high": 0, "medium": 1, "low": 2}.get(x.get("priority", "medium"), 1))
    
    for source in sources:
        source = enhance_source_metadata(source)
        
        try:
            if source["type"] == "rss":
                feed = feedparser.parse(source["url"])
                
                # Get more articles for high-priority sources
                max_articles = source["max_articles"]
                if source.get("priority") == "high":
                    max_articles *= 2
                
                for entry in feed.entries[:max_articles]:
                    # Skip old articles unless it's breaking news
                    published = entry.get("published") or entry.get("updated") or ""
                    if not is_recent_article(published, hours_threshold=72):
                        continue
                    
                    # Create content hash for deduplication
                    content_hash = create_content_hash(entry.title, entry.link)
                    if content_hash in existing_hashes:
                        continue
                    
                    # Get article content for better analysis
                    article_content = get_article_content(entry.link)
                    
                    # Check for breaking news indicators
                    is_breaking = extract_breaking_news_indicators(
                        entry.title, 
                        article_content,
                        source.get("relevance_keywords", [])
                    )
                    
                    # Score relevance
                    relevance_score = score_article_relevance(
                        entry.title,
                        article_content,
                        source.get("topics", []),
                        source.get("relevance_keywords", [])
                    )
                    
                    # Skip low-relevance articles unless breaking
                    if relevance_score < 0.3 and not is_breaking:
                        continue
                    
                    # Enhanced summarization
                    fallback = getattr(entry, "summary", "") or getattr(entry, "description", "")
                    summary = enhanced_summarize_article(
                        entry.link, 
                        article_content or fallback,
                        is_breaking=is_breaking,
                        relevance_score=relevance_score
                    )
                    
                    article = Article(
                        source=source["name"],
                        title=entry.title,
                        url=entry.link,
                        published=published,
                        summary=summary,
                        topics=source.get("topics", []),
                        content_hash=content_hash,
                        relevance_score=relevance_score,
                        is_breaking=is_breaking
                    )
                    
                    articles.append(article)
                    existing_hashes.add(content_hash)
        
        except Exception as e:
            print(f"Error processing source {source['name']}: {e}")
            continue
    
    # Sort by breaking news first, then relevance, then recency
    articles.sort(key=lambda x: (not x.is_breaking, -x.relevance_score, x.published), reverse=False)
    
    return articles

def main():
    """Main execution function."""
    parser = argparse.ArgumentParser(description="Enhanced article fetcher")
    parser.add_argument(
        "-c",
        "--config",
        default=os.getenv("ENHANCED_FEEDS_FILE", "feeds/enhanced_sources.yaml"),
        help="Path to YAML configuration file"
    )
    args = parser.parse_args()

    articles = fetch_enhanced_articles(args.config)
    
    # Convert to JSON format
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
            "is_breaking": article.is_breaking
        }
        summaries.append(summary_data)
    
    # Limit total articles to prevent overwhelming
    summaries = summaries[:50]
    
    # Save with metadata
    output = {
        "generated_at": datetime.now().isoformat(),
        "total_articles": len(summaries),
        "breaking_news_count": sum(1 for s in summaries if s["is_breaking"]),
        "articles": summaries
    }
    
    os.makedirs("data", exist_ok=True)
    with open("data/summaries.json", "w") as f:
        json.dump(output, f, indent=2)
    
    print(f"✅ Processed {len(summaries)} articles ({output['breaking_news_count']} breaking)")

if __name__ == "__main__":
    main()