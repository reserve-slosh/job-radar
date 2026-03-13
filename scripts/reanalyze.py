"""Re-runs LLM analysis on jobs where new scores are missing.

Selects jobs where score_future IS NULL AND fit_score >= 3, then calls the analyzer
and writes results back via update_analysis. Does not touch bewerbung_status or
status_changed_at.

Usage:
    uv run python scripts/reanalyze.py
    uv run python scripts/reanalyze.py --dry-run
    uv run python scripts/reanalyze.py --limit 10
    uv run python scripts/reanalyze.py --db /path/to/job_radar.db
"""

import argparse
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

from job_radar.config import Config, load_profiles
from job_radar.db.models import get_connection, update_analysis
from job_radar.pipeline.analyzer import analyze

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_DEFAULT_LIMIT = 25


def _fetch_candidates(db_path: str, limit: int) -> list[dict]:
    with get_connection(db_path) as conn:
        rows = conn.execute(
            """
            SELECT refnr, titel, arbeitgeber, fit_score, raw_text, search_profile
            FROM jobs
            WHERE score_future IS NULL
              AND fit_score >= 3
            ORDER BY fit_score DESC, fetched_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def _resolve_profile(candidates, profile_key: str) -> tuple[str, str]:
    """Returns (profile_text, fit_score_context) for a search_profile key like 'flemming_koeln'."""
    candidate_name = profile_key.split("_")[0] if profile_key else ""
    search_profile_name = "_".join(profile_key.split("_")[1:]) if "_" in profile_key else ""

    candidate = next((c for c in candidates if c.name == candidate_name), None)
    if candidate is None:
        return "", ""

    search_profile = next(
        (sp for sp in candidate.search_profiles if sp.name == search_profile_name),
        candidate.search_profiles[0] if candidate.search_profiles else None,
    )

    profile_text = candidate.profile_text if candidate else ""
    fit_score_context = search_profile.fit_score_context if search_profile else ""
    return profile_text, fit_score_context


def reanalyze(db_path: str, api_key: str, profiles_dir: str, limit: int, dry_run: bool) -> None:
    jobs = _fetch_candidates(db_path, limit)

    if not jobs:
        logger.info("No jobs match criteria (score_future IS NULL AND fit_score >= 3).")
        return

    logger.info("Found %d job(s) to reanalyze (limit=%d).", len(jobs), limit)

    if dry_run:
        logger.info("[dry-run] Would reanalyze:")
        for job in jobs:
            logger.info(
                "  [fit=%s] %s @ %s  (refnr=%s, profile=%s)",
                job["fit_score"],
                job["titel"] or "—",
                job["arbeitgeber"] or "—",
                job["refnr"],
                job["search_profile"] or "—",
            )
        return

    candidates = load_profiles(profiles_dir)

    for job in jobs:
        refnr = job["refnr"]
        titel = job["titel"] or "—"
        arbeitgeber = job["arbeitgeber"] or "—"
        fit_before = job["fit_score"]

        profile_text, fit_score_context = _resolve_profile(candidates, job.get("search_profile", ""))

        logger.info("Analyzing: [fit=%s] %s @ %s", fit_before, titel, arbeitgeber)

        result = analyze(
            job["raw_text"] or "",
            api_key=api_key,
            profile_text=profile_text,
            fit_score_context=fit_score_context,
        )

        update_analysis(db_path, refnr, result)

        logger.info(
            "  → fit=%s  future=%s  salary=%s  chance=%s",
            result.get("fit_score"),
            result.get("future"),
            result.get("salary"),
            result.get("chance"),
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Re-run LLM analysis on jobs missing new score dimensions"
    )
    parser.add_argument(
        "--db",
        default=os.environ.get("DB_PATH", "job_radar.db"),
        help="Path to the SQLite database (default: $DB_PATH or job_radar.db)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=_DEFAULT_LIMIT,
        help=f"Maximum number of jobs to process (default: {_DEFAULT_LIMIT})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show which jobs would be reanalyzed without making any API calls",
    )
    args = parser.parse_args()

    config = Config(db_path=args.db)

    if not args.dry_run and not config.anthropic_api_key:
        logger.error("ANTHROPIC_API_KEY not set. Use --dry-run or set the key.")
        sys.exit(1)

    reanalyze(
        db_path=args.db,
        api_key=config.anthropic_api_key,
        profiles_dir=config.profiles_dir,
        limit=args.limit,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
