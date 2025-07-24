import openai
import os
from datetime import datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from newspaper import Article

openai.api_key = os.getenv("OPENAI_API_KEY")


def _simple_summary(text: str) -> str:
    """Return first two sentences from the provided text."""
    sentences = [s.strip() for s in text.replace("\n", " ").split(". ") if s.strip()]
    return (". ".join(sentences[:2]) + ("." if sentences else "")).strip()

def summarize_article(url: str, fallback_text: str | None = None) -> str:
    """Summarize an article URL using OpenAI if available with a fallback."""
    text = ""
    try:
        article = Article(url)
        article.download()
        article.parse()
        text = article.text
    except Exception:
        if fallback_text:
            text = fallback_text
    if not text:
        return "Summary not available."

    if openai.api_key:
        try:
            prompt = f"Summarize the following blog post in 2 sentences:\n{text}"
            result = openai.ChatCompletion.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
            )
            return result.choices[0].message["content"].strip()
        except Exception:
            pass

    return _simple_summary(text)

def scrape_blog(url: str, limit: int = 5):
    """Attempt to scrape a blog listing page and return recent entries."""
    try:
        response = requests.get(url, timeout=10)
        soup = BeautifulSoup(response.text, "html.parser")
        entries = []
        for link in soup.find_all("a"):
            href = link.get("href")
            if not href:
                continue
            title = link.get_text(strip=True)
            if not title:
                continue
            article_url = urljoin(url, href)
            time_tag = link.find_previous("time")
            date = time_tag.get("datetime") if time_tag else str(datetime.now())
            entries.append({"title": title, "url": article_url, "date": date})
            if len(entries) >= limit:
                break
        return entries or [{"title": "Placeholder", "url": url, "date": str(datetime.now())}]
    except Exception:
        return [{"title": "Placeholder", "url": url, "date": str(datetime.now())}]
