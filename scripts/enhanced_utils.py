import os
import re
import requests
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from urllib.parse import urljoin
import openai
from bs4 import BeautifulSoup
from newspaper import Article
import spacy
from textstat import flesch_reading_ease
from collections import Counter

# Initialize OpenAI with new API
client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Load spaCy model for NLP (fallback to basic if not available)
try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    nlp = None

BREAKING_NEWS_INDICATORS = [
    "breaking", "urgent", "just in", "developing", "alert", "emergency",
    "critical", "major", "significant", "important update", "announcement",
    "launches", "releases", "acquires", "partnership", "funding", "ipo",
    "vulnerability", "breach", "outage", "incident", "crisis"
]

AI_RELEVANCE_KEYWORDS = [
    "artificial intelligence", "ai", "machine learning", "ml", "deep learning",
    "neural network", "llm", "large language model", "gpt", "transformer",
    "chatbot", "generative", "computer vision", "nlp", "natural language",
    "automation", "robotics", "algorithm", "data science", "predictive",
    "classification", "regression", "reinforcement learning", "supervised",
    "unsupervised", "tensorflow", "pytorch", "hugging face", "openai",
    "anthropic", "google ai", "microsoft ai", "nvidia ai", "stable diffusion",
    "midjourney", "dalle", "claude", "bard", "copilot", "embedding",
    "fine-tuning", "prompt engineering", "rag", "vector database"
]

def get_article_content(url: str, timeout: int = 15) -> Optional[str]:
    """Enhanced article content extraction with better error handling."""
    try:
        # Try newspaper3k first (more reliable)
        article = Article(url)
        article.download()
        article.parse()
        
        if article.text and len(article.text) > 200:
            return article.text
        
        # Fallback to manual scraping
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        }
        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Remove unwanted elements
        for element in soup(['script', 'style', 'nav', 'footer', 'aside', 'advertisement']):
            element.decompose()
        
        # Try to find main content areas
        content_selectors = [
            'article', '[role="main"]', '.post-content', '.entry-content',
            '.article-content', '.content', 'main', '.post-body'
        ]
        
        text = ""
        for selector in content_selectors:
            content_area = soup.select_one(selector)
            if content_area:
                text = content_area.get_text(separator=' ', strip=True)
                if len(text) > 200:
                    break
        
        if not text:
            # Last resort: get all p tags
            paragraphs = soup.find_all('p')
            text = ' '.join([p.get_text(strip=True) for p in paragraphs])
        
        return text if len(text) > 100 else None
        
    except Exception as e:
        print(f"Failed to extract content from {url}: {e}")
        return None

def extract_breaking_news_indicators(title: str, content: Optional[str], keywords: List[str]) -> bool:
    """Detect if an article contains breaking news indicators."""
    text_to_check = f"{title.lower()} {(content or '').lower()}"
    
    # Check for explicit breaking news indicators
    for indicator in BREAKING_NEWS_INDICATORS:
        if indicator in text_to_check:
            return True
    
    # Check for source-specific keywords
    for keyword in keywords:
        if keyword.lower() in text_to_check:
            return True
    
    # Check for recent product launches, funding announcements, etc.
    recent_patterns = [
        r'\b(announced|launches|released|introduces)\b.*\b(today|yesterday|this week)\b',
        r'\$\d+[mb].*\b(funding|investment|round)\b',
        r'\b(acquired|acquisition|merger)\b',
        r'\b(ipo|public offering)\b'
    ]
    
    for pattern in recent_patterns:
        if re.search(pattern, text_to_check, re.IGNORECASE):
            return True
    
    return False

def score_article_relevance(title: str, content: Optional[str], 
                          source_topics: List[str], keywords: List[str]) -> float:
    """Score article relevance based on AI/tech content and source topics."""
    if not content:
        content = ""
    
    text = f"{title} {content}".lower()
    score = 0.0
    
    # Base score from AI relevance keywords
    ai_matches = sum(1 for keyword in AI_RELEVANCE_KEYWORDS if keyword in text)
    score += min(ai_matches * 0.1, 0.5)
    
    # Score from source topics
    topic_matches = sum(1 for topic in source_topics if topic.lower() in text)
    score += min(topic_matches * 0.15, 0.3)
    
    # Score from custom keywords
    keyword_matches = sum(1 for keyword in keywords if keyword.lower() in text)
    score += min(keyword_matches * 0.1, 0.2)
    
    # Boost for technical depth (longer articles with technical terms)
    if len(text) > 2000:
        technical_terms = ['api', 'framework', 'algorithm', 'model', 'data', 'system', 'platform']
        tech_count = sum(1 for term in technical_terms if term in text)
        score += min(tech_count * 0.05, 0.2)
    
    # Penalize if too short or generic
    if len(text) < 500:
        score *= 0.7
    
    return min(score, 1.0)

def detect_duplicate_content(articles: List[Dict]) -> List[str]:
    """Detect duplicate articles using title similarity and URL comparison."""
    if not nlp:
        # Fallback: simple title comparison
        seen_titles = set()
        duplicates = []
        for article in articles:
            title_normalized = re.sub(r'[^\w\s]', '', article['title'].lower()).strip()
            if title_normalized in seen_titles:
                duplicates.append(article['url'])
            else:
                seen_titles.add(title_normalized)
        return duplicates
    
    # Advanced duplicate detection using spaCy
    duplicates = []
    processed_articles = []
    
    for article in articles:
        is_duplicate = False
        current_doc = nlp(article['title'])
        
        for prev_article in processed_articles:
            prev_doc = nlp(prev_article['title'])
            similarity = current_doc.similarity(prev_doc)
            
            if similarity > 0.85:  # High similarity threshold
                duplicates.append(article['url'])
                is_duplicate = True
                break
        
        if not is_duplicate:
            processed_articles.append(article)
    
    return duplicates

def enhanced_summarize_article(url: str, content: str, 
                              is_breaking: bool = False, 
                              relevance_score: float = 0.5) -> str:
    """Enhanced AI-powered article summarization with context awareness."""
    
    if not content or len(content) < 50:
        return "Summary not available - insufficient content."
    
    # Truncate very long content
    if len(content) > 8000:
        content = content[:8000] + "..."
    
    if not client.api_key:
        return _enhanced_fallback_summary(content, is_breaking)
    
    try:
        # Dynamic prompt based on article characteristics
        if is_breaking:
            prompt = f"""Summarize this breaking news article in 2-3 concise sentences, focusing on:
1. What happened (the main event/announcement)
2. Why it's significant
3. Key implications or next steps

Article: {content}"""
        elif relevance_score > 0.7:
            prompt = f"""Summarize this technical article in 2-3 sentences, focusing on:
1. The main technical concept or innovation
2. Practical applications or benefits
3. Target audience or use cases

Article: {content}"""
        else:
            prompt = f"""Summarize this article in 2 clear sentences focusing on the key points and main takeaways:

Article: {content}"""
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",  # More cost-effective for summaries
            messages=[
                {"role": "system", "content": "You are an expert technical writer who creates concise, informative summaries for a tech-savvy audience."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=150,
            temperature=0.3
        )
        
        summary = response.choices[0].message.content.strip()
        
        # Quality check
        if len(summary) < 20 or "I cannot" in summary or "unable to" in summary:
            return _enhanced_fallback_summary(content, is_breaking)
        
        return summary
        
    except Exception as e:
        print(f"OpenAI summarization failed for {url}: {e}")
        return _enhanced_fallback_summary(content, is_breaking)

def _enhanced_fallback_summary(content: str, is_breaking: bool = False) -> str:
    """Enhanced fallback summarization without AI."""
    if not content:
        return "Summary not available."
    
    # Clean and normalize text
    sentences = re.split(r'[.!?]+', content.replace('\n', ' '))
    sentences = [s.strip() for s in sentences if len(s.strip()) > 20]
    
    if not sentences:
        return "Summary not available."
    
    # For breaking news, prioritize sentences with action words
    if is_breaking:
        action_words = ['announced', 'launched', 'released', 'acquired', 'raised', 'partnered']
        priority_sentences = []
        for sentence in sentences[:10]:  # Check first 10 sentences
            if any(word in sentence.lower() for word in action_words):
                priority_sentences.append(sentence)
        
        if priority_sentences:
            sentences = priority_sentences + [s for s in sentences if s not in priority_sentences]
    
    # Take first 2-3 most informative sentences
    summary_sentences = []
    for sentence in sentences[:5]:
        if len(sentence) > 30 and len(sentence) < 200:  # Filter by length
            summary_sentences.append(sentence)
            if len(summary_sentences) >= 2:
                break
    
    if not summary_sentences:
        summary_sentences = sentences[:2]
    
    summary = '. '.join(summary_sentences[:2]) + '.'
    
    # Clean up formatting
    summary = re.sub(r'\s+', ' ', summary)
    summary = summary.strip()
    
    return summary if len(summary) > 20 else "Summary not available."

def analyze_content_quality(content: str) -> Dict[str, float]:
    """Analyze content quality metrics."""
    if not content:
        return {"readability": 0, "technical_depth": 0, "informativeness": 0}
    
    # Readability score
    try:
        readability = flesch_reading_ease(content) / 100.0
    except:
        readability = 0.5
    
    # Technical depth (presence of technical terms)
    technical_terms = [
        'algorithm', 'framework', 'api', 'database', 'architecture', 'system',
        'model', 'analysis', 'performance', 'optimization', 'implementation'
    ]
    tech_score = min(sum(1 for term in technical_terms if term in content.lower()) / 10.0, 1.0)
    
    # Informativeness (content length and structure)
    info_score = min(len(content) / 5000.0, 1.0)  # Normalize by expected article length
    
    return {
        "readability": readability,
        "technical_depth": tech_score,
        "informativeness": info_score
    }