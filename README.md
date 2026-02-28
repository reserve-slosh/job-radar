# job-radar

job-radar fetches job postings from two sources — Bundesagentur für Arbeit and Arbeitnow — filters them by location and title keywords, analyzes each posting via Claude Haiku (fit score, seniority, remote status, tech stack), and stores the results in a local SQLite database. A separate script generates LaTeX cover letter drafts for selected jobs using Claude Sonnet with web search. The pipeline is designed to run repeatedly: jobs are skipped if their modification timestamp hasn't changed, and re-analyzed if it has.

## Stack

- Python 3.11+, managed with `uv`
- `requests`, `beautifulsoup4` — HTTP and HTML parsing
- `anthropic` — LLM analysis (Haiku) and cover letter generation (Sonnet)
- `sqlite3` — local storage, no external DB required
- `rich` — terminal output
- `python-dotenv` — config via `.env`

## Project structure

```
job_radar/
├── sources/        # One module per data source
├── pipeline/       # extractor, analyzer
├── db/             # schema, queries, models
└── config.py       # config dataclasses
scripts/
├── run_pipeline.py # pipeline entrypoint
├── show_jobs.py    # tabular DB viewer
└── bewerbung.py    # cover letter generator
profiles/
└── profile.txt     # candidate profile fed to the LLM
templates/
└── anschreiben_template.tex
```

## Setup

```bash
uv venv && source .venv/bin/activate
uv pip install -e .
```

Create a `.env` file in the project root:

```
ANTHROPIC_API_KEY=sk-ant-...
DB_PATH=job_radar.db          # optional, this is the default
```

The database is created automatically on first run.

## Usage

**Run the pipeline** (fetches, analyzes, stores):

```bash
python scripts/run_pipeline.py
```

**View jobs** in the terminal:

```bash
python scripts/show_jobs.py
python scripts/show_jobs.py --min-score 4
python scripts/show_jobs.py --profile koeln --min-score 3
python scripts/show_jobs.py --bewerbung-status entwurf
```

**Generate a cover letter** — interactive job picker:

```bash
python scripts/bewerbung.py
```

Or pass a specific `refnr` directly:

```bash
python scripts/bewerbung.py --refnr <refnr>
```

Output is written to `output/bewerbungen/` as a `.tex` file. The job's `bewerbung_status` is set to `entwurf` and the raw LaTeX is stored in `bewerbung_entwurf` in the DB.

## Architecture notes

**Sources** (`job_radar/sources/`) are the extension point for new job feeds. Each source implements `fetch_job_list(config)` and returns a list of dicts normalized to the shared pipeline schema (`refnr`, `titel`, `arbeitgeber`, `ort`, `raw_text`, `modifikationsTimestamp`, etc.). Arbeitsagentur additionally implements `fetch_job_detail()` to scrape the full posting; Arbeitnow returns the description inline via the API. Adding a new source means adding one module and wiring it into `run_pipeline.py`.

**`search_profile`** is a TEXT column on both `jobs` and `runs` (default: `koeln`). It's intended as a tag for multi-mode use — e.g. running the pipeline with different search configs for different cities or job types and filtering results accordingly with `show_jobs.py --profile`.

**LLM analysis** falls back to a stub (all fields `None`) if `ANTHROPIC_API_KEY` is not set, so the pipeline runs without an API key — jobs are fetched and stored, but without scores or summaries. Re-analysis is triggered only when `modifikationsTimestamp` changes, so API calls are not repeated for unchanged postings.

**Pipeline run tracking** — each execution of `run_pipeline.py` writes a row to the `runs` table with counts (new, updated, skipped, failed) and status (`running` → `success` or `error`).
