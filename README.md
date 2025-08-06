# Tech Blog Digest

A GitHub Actions-based crawler that scans top engineering and AI blogs daily, summarizes new posts, and outputs a JSON digest.

## Features

- RSS powered scraping
- GPT-4o-powered summarization with a local fallback
- GitHub Actions automation
- Output to files named `data/summaries_<date>.json`

## Setup

1. Add your `OPENAI_API_KEY` as a GitHub secret.
2. Install dependencies with `pip install -r requirements.txt`.
3. Enable GitHub Actions.
4. Check the `data/` folder for daily updates.

## Sources

Configured in `feeds/sources.yaml`. A wide variety of AI and engineering blogs are listed including Athropic, OpenAI, Google, Microsoft and more. Add your own entries to expand coverage.
