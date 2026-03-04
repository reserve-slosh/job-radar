# job-radar

job-radar fetches job postings from two sources — Bundesagentur für Arbeit and Arbeitnow — filters them by location and title keywords, analyzes each posting via Claude Haiku (fit score, seniority, remote status, tech stack), and stores the results in a local SQLite database. The pipeline supports multiple candidates and search profiles, iterating over all configured combinations automatically. A Streamlit dashboard provides the primary UI for browsing results and generating cover letters. A separate script generates LaTeX cover letter drafts using Claude Sonnet with extended thinking and web search. The pipeline is designed to run repeatedly: jobs are skipped if their modification timestamp hasn't changed, and re-analyzed if it has.

## Stack

- Python 3.11+, managed with `uv`
- `requests`, `beautifulsoup4` — HTTP and HTML parsing
- `anthropic` — LLM analysis (Haiku) and cover letter generation (Sonnet)
- `sqlite3` — local storage, no external DB required
- `streamlit` — dashboard UI
- `pyyaml` — candidate profile loading
- `rich` — terminal output
- `python-dotenv` — config via `.env`

## Project structure

```
job_radar/
├── sources/        # One module per data source
├── pipeline/       # extractor, analyzer
├── db/             # schema, queries, models
└── config.py       # SearchProfile, CandidateProfile, load_profiles
scripts/
├── run_pipeline.py # pipeline entrypoint, iterates candidates × search_profiles
├── dashboard.py    # Streamlit dashboard (main UI)
├── show_jobs.py    # legacy terminal viewer
└── bewerbung.py    # cover letter generator (CLI)
profiles/
├── flemming.yaml   # candidate profile + search profiles
└── hjoerdis.yaml   # candidate profile + search profiles
templates/
└── anschreiben_template.tex
```

## Setup

```bash
uv sync
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
uv run python scripts/run_pipeline.py
```

Run without LLM analysis (no API key needed):

```bash
uv run python scripts/run_pipeline.py --no-llm
```

**Launch the dashboard:**

```bash
uv run streamlit run scripts/dashboard.py
```

Three tabs: **Jobs** (filterable table with score, seniority, remote, status filters), **Detail & Bewerbung** (full job view, inline cover letter generation, `.tex` download, LLM analysis expander), **Runs** (pipeline history + manual trigger).

**Generate a cover letter** from the CLI — interactive job picker:

```bash
uv run python scripts/bewerbung.py --candidate flemming
```

Or pass a specific `refnr` directly:

```bash
uv run python scripts/bewerbung.py --candidate flemming --refnr <refnr>
```

Output is written to `output/bewerbungen/` as a `.tex` file. The job's `bewerbung_status` is set to `entwurf`, the raw LaTeX is stored in `bewerbung_entwurf`, and the full LLM response (analysis + cover letter fields) is stored in `bewerbung_analyse` in the DB.

## Candidate profiles

Each candidate is a YAML file in `profiles/`. Required keys:

```yaml
name: flemming

profile_text: |
  <free-form text fed to the LLM — background, skills, preferences, cover letter templates>

search_profiles:
  - name: koeln
    enabled: true
    remote_only: false
    location_filter:
      - köln
      - cologne
    arbeitsagentur_queries:
      - was: "Data Engineer"
        wo: "50667"
        umkreis: 25
    title_keywords:
      - data
      - engineer
    title_exclude:
      - head of
      - director
    fit_score_context: |
      <scoring guidance fed to the LLM>
```

The pipeline iterates over all enabled `search_profiles` for each candidate. DB keys follow the pattern `{candidate_name}_{profile_name}` (e.g. `flemming_koeln`).

To add a new candidate: create `profiles/<name>.yaml` with the above structure. No code changes required.

## Architecture notes

**Sources** (`job_radar/sources/`) are the extension point for new job feeds. Each source implements `fetch_job_list(config, search_profile)` and returns a list of dicts normalized to the shared pipeline schema (`refnr`, `titel`, `arbeitgeber`, `ort`, `raw_text`, `modifikationsTimestamp`, etc.). Arbeitsagentur additionally implements `fetch_job_detail()` to scrape the full posting; Arbeitnow returns the description inline via the API. Adding a new source means adding one module and wiring it into `run_pipeline.py`.

**`SearchProfile`** (in `config.py`) owns all filter logic — location matching, title keyword inclusion/exclusion, and fit score context. `ArbeitnowConfig` and `ArbeitsamtConfig` hold only connection parameters. The pipeline passes the active `SearchProfile` into each source so filtering is consistent across sources.

**LLM analysis** falls back to a stub (all fields `None`) if `ANTHROPIC_API_KEY` is not set, so the pipeline runs without an API key — jobs are fetched and stored, but without scores or summaries. Re-analysis is triggered only when `modifikationsTimestamp` changes, so API calls are not repeated for unchanged postings.

**Pipeline run tracking** — each execution of `run_pipeline.py` writes a row to the `runs` table with counts (new, updated, skipped, failed) and status (`running` → `success` or `error`).

**Cover letter generation** (`bewerbung.py`, also callable from the dashboard) uses Claude Sonnet with extended thinking and web search. The prompt instructs the model to research the company across three phases (culture, tech stack, market position) before writing. The full JSON response — including analysis fields (`unternehmens_satz`, `kurzprofil`, style decision) and the cover letter itself — is stored in `bewerbung_analyse` separately from the pipeline's `llm_output`.
