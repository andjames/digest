import openai, requests, os
from bs4 import BeautifulSoup
from datetime import datetime

openai.api_key = os.getenv("OPENAI_API_KEY")

def summarize_article(url):
    try:
        response = requests.get(url, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        text = ' '.join(p.get_text() for p in soup.find_all('p')[:5])
        prompt = f"Summarize the following blog post in 2 sentences:\n{text}"
        result = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}]
        )
        return result.choices[0].message["content"].strip()
    except Exception as e:
        return "Summary not available."

def scrape_blog(url):
    return [{"title": "Placeholder", "url": url, "date": str(datetime.now())}]
