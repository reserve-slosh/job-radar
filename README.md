# job-radar

Automated job listing aggregator and analyzer. Fetches job postings from the Bundesagentur für Arbeit, extracts the relevant content, and uses an LLM to produce structured summaries and fit scores.

## What it does

- Pulls job listings from the Arbeitsagentur API based on configurable search parameters
- Scrapes full job descriptions from the detail pages
- Analyzes each posting via Claude Haiku (Anthropic) and stores structured results in a local SQLite database
- Skips already-processed listings on subsequent runs

## Setup

**Requirements:** Python 3.11+, [uv](https://github.com/astral-sh/uv)
```bash
git clone https://github.com/<your-username>/job-radar.git
cd job-radar
uv venv && source .venv/bin/activate
uv pip install -e .
cp .env.example .env  # add your ANTHROPIC_API_KEY
```

## Usage
```bash
python scripts/run_pipeline.py
```

## Configuration

Search parameters (location, job title, radius etc.) can be adjusted in `job_radar/config.py` under `ArbeitsamtConfig`.

## Roadmap

- Cronjob setup for automated daily runs
- Additional job sources (e.g. StepStone, LinkedIn)
- Simple output view / reporting
