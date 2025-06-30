# Tech Blog Digest

A GitHub Actions-based crawler that scans top engineering and AI blogs daily, summarizes new posts, and outputs a JSON digest.

## Features

- RSS and HTML scraping
- GPT-4o-powered summarization
- GitHub Actions automation
- Output to `data/summaries.json`

## Setup

1. Add your `OPENAI_API_KEY` as a GitHub secret.
2. Enable GitHub Actions.
3. Check the `data/` folder for daily updates.

## Sources

Configured in `feeds/sources.yaml`
