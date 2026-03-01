import argparse
import logging
import logging.handlers
import json
import os
from pathlib import Path
from job_radar.config import Config, load_profiles, CandidateProfile, SearchProfile
from job_radar.db.models import (
    init_db, job_exists, insert_job, update_job, get_modifikations_timestamp,
    PipelineRun, insert_run, finish_run,
)
from job_radar.sources.arbeitsagentur import fetch_job_list as fetch_arbeitsagentur_jobs
from job_radar.sources.arbeitnow import fetch_job_list as fetch_arbeitnow_jobs
from job_radar.pipeline.extractor import build_job
from job_radar.pipeline.analyzer import analyze

_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s — %(message)s"

logging.basicConfig(level=logging.INFO, format=_LOG_FORMAT)

_log_dir = Path(__file__).resolve().parent.parent / "logs"
_log_dir.mkdir(exist_ok=True)
_file_handler = logging.handlers.RotatingFileHandler(
    _log_dir / "pipeline.log",
    maxBytes=5 * 1024 * 1024,
    backupCount=3,
)
_file_handler.setFormatter(logging.Formatter(_LOG_FORMAT))
logging.getLogger().addHandler(_file_handler)

logger = logging.getLogger(__name__)


def _process_batch(
    raw_jobs: list[dict],
    source: str,
    config: Config,
    candidate: CandidateProfile,
    search_profile: SearchProfile,
    no_llm: bool = False,
) -> tuple[int, int, int, int]:
    """Processes a list of raw job dicts for a given source and profile combination.

    Returns (new, skipped, reanalyzed, failed).
    """
    profile_key = f"{candidate.name}_{search_profile.name}"
    new, skipped, reanalyzed, failed = 0, 0, 0, 0

    for raw in raw_jobs:
        refnr = raw.get("refnr")
        if not refnr:
            continue

        incoming_ts = raw.get("modifikationsTimestamp")
        is_existing = job_exists(config.db_path, refnr)
        if is_existing:
            stored_ts = get_modifikations_timestamp(config.db_path, refnr)
            if stored_ts == incoming_ts:
                logger.debug("Übersprungen (unverändert): %s", refnr)
                skipped += 1
                continue
            logger.info("Geändert, re-analysiere: %s", refnr)

        job = build_job(raw, source=source)
        if job is None:
            failed += 1
            continue

        if not search_profile.matches_title({"titel": job.titel}) or \
           not search_profile.matches_location({"ort": job.ort, "remote": job.remote == "remote"}):
            skipped += 1
            continue

        job.search_profile = profile_key

        result = analyze(
            job.raw_text or "",
            api_key="" if no_llm else config.anthropic_api_key,
            profile_text=candidate.profile_text,
            fit_score_context=search_profile.fit_score_context,
        )

        job.titel_normalisiert = result.get("titel_normalisiert")
        job.remote = result.get("remote")
        job.vertragsart = result.get("vertragsart")
        job.seniority = result.get("seniority")
        job.tech_stack = json.dumps(result.get("tech_stack")) if result.get("tech_stack") else None
        job.zusammenfassung = result.get("zusammenfassung")
        job.fit_score = result.get("fit_score")
        job.llm_output = json.dumps(result)

        if is_existing:
            update_job(config.db_path, job)
            logger.info("Aktualisiert: %s — %s", refnr, job.titel)
            reanalyzed += 1
        else:
            insert_job(config.db_path, job)
            logger.info("Neu gespeichert: %s — %s", refnr, job.titel)
            new += 1

    return new, skipped, reanalyzed, failed


def _run_profile(
    candidate: CandidateProfile,
    search_profile: SearchProfile,
    config: Config,
    no_llm: bool = False,
) -> None:
    """Runs the full pipeline for one candidate × search_profile combination."""
    profile_key = f"{candidate.name}_{search_profile.name}"
    logger.info("=== Profil: %s ===", profile_key)

    run_id = insert_run(
        config.db_path,
        PipelineRun(source="all", search_profile=profile_key),
    )

    try:
        logger.info("--- Quelle: Arbeitsagentur ---")
        aa_jobs = fetch_arbeitsagentur_jobs(config.arbeitsamt, search_profile)
        logger.info("%d Jobs gefunden", len(aa_jobs))
        aa = _process_batch(aa_jobs, "arbeitsagentur", config, candidate, search_profile, no_llm)

        logger.info("--- Quelle: Arbeitnow ---")
        an_jobs = fetch_arbeitnow_jobs(config.arbeitnow, search_profile)
        logger.info("%d Jobs gefunden", len(an_jobs))
        an = _process_batch(an_jobs, "arbeitnow", config, candidate, search_profile, no_llm)

        aa_new, aa_skipped, aa_reanalyzed, aa_failed = aa
        an_new, an_skipped, an_reanalyzed, an_failed = an
        totals = tuple(x + y for x, y in zip(aa, an))

        logger.info(
            "[%s] Arbeitsagentur — Neu: %d, Übersprungen: %d, Re-analysiert: %d, Fehlgeschlagen: %d",
            profile_key, *aa,
        )
        logger.info(
            "[%s] Arbeitnow     — Neu: %d, Übersprungen: %d, Re-analysiert: %d, Fehlgeschlagen: %d",
            profile_key, *an,
        )
        logger.info(
            "[%s] Gesamt        — Neu: %d, Übersprungen: %d, Re-analysiert: %d, Fehlgeschlagen: %d",
            profile_key, *totals,
        )

        finish_run(
            config.db_path,
            run_id,
            jobs_fetched=len(aa_jobs) + len(an_jobs),
            jobs_new=aa_new + an_new,
            jobs_updated=aa_reanalyzed + an_reanalyzed,
            jobs_skipped=aa_skipped + an_skipped,
            jobs_failed=aa_failed + an_failed,
            status="success",
        )

    except Exception as e:
        finish_run(
            config.db_path,
            run_id,
            jobs_fetched=0,
            jobs_new=0,
            jobs_updated=0,
            jobs_skipped=0,
            jobs_failed=0,
            status="error",
            error_msg=str(e),
        )
        raise


def run() -> None:
    parser = argparse.ArgumentParser(description="Job-Radar Pipeline")
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="LLM-Analyse überspringen (nur fetchen & filtern, kein API-Key nötig)",
    )
    args = parser.parse_args()

    config = Config()
    init_db(config.db_path)

    candidates = load_profiles(config.profiles_dir)
    if not candidates:
        logger.warning("Keine Profile in '%s' gefunden.", config.profiles_dir)
        return

    # Optional: filter via PIPELINE_CANDIDATES env var (set by dashboard trigger)
    pipeline_filter = os.environ.get("PIPELINE_CANDIDATES")
    if pipeline_filter:
        allowed = {name.strip().lower() for name in pipeline_filter.split(",")}
        candidates = [c for c in candidates if c.name.lower() in allowed]
        logger.info("Kandidaten-Filter aktiv: %s", [c.name for c in candidates])

    for candidate in candidates:
        for search_profile in candidate.search_profiles:
            _run_profile(candidate, search_profile, config, no_llm=args.no_llm)


if __name__ == "__main__":
    run()