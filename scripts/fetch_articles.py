import feedparser
import yaml
import json
import os
from datetime import datetime, timedelta
from dateutil import parser as date_parser
from utils import summarize_article, scrape_blog

with open("feeds/sources.yaml") as f:
    sources = yaml.safe_load(f)

summaries = []
cutoff = datetime.utcnow() - timedelta(days=7)

for source in sources:
    if source["type"] == "rss":
        feed = feedparser.parse(source["url"])
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
            summary = summarize_article(entry.link, fallback)
            summaries.append({
                "source": source["name"],
                "title": entry.title,
                "url": entry.link,
                "published": published,
                "summary": summary,
                "topics": source.get("topics", [])
            })

    elif source["type"] == "scrape":
        scraped = scrape_blog(source["url"])
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

            summary = summarize_article(entry["url"], entry.get("summary"))
            summaries.append({
                "source": source["name"],
                "title": entry["title"],
                "url": entry["url"],
                "published": pub_date_str,
                "summary": summary,
                "topics": source.get("topics", [])
            })

os.makedirs("data", exist_ok=True)
today = datetime.utcnow().strftime("%Y-%m-%d")
output_file = f"data/summaries_{today}.json"
with open(output_file, "w") as f:
    json.dump(summaries, f, indent=2)

