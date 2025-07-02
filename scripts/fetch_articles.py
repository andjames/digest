import feedparser, yaml, json, os
from utils import summarize_article, scrape_blog

with open("feeds/sources.yaml") as f:
    sources = yaml.safe_load(f)

summaries = []

for source in sources:
    if source["type"] == "rss":
        feed = feedparser.parse(source["url"])
        for entry in feed.entries[:3]:
            summary = summarize_article(entry.link)
            published = entry.get("published") or entry.get("updated") or ""
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
            summary = summarize_article(entry["url"])
            summaries.append({
                "source": source["name"],
                "title": entry["title"],
                "url": entry["url"],
                "published": entry["date"],
                "summary": summary,
                "topics": source.get("topics", [])
            })

os.makedirs("data", exist_ok=True)
with open("data/summaries.json", "w") as f:
    json.dump(summaries, f, indent=2)
