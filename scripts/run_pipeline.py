import logging
import logging.handlers
import json
from pathlib import Path
from job_radar.config import Config
from job_radar.db.models import init_db, job_exists, insert_job, update_job, get_modifikations_timestamp
from job_radar.sources.arbeitsagentur import fetch_job_list
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


def run():
    config = Config()
    init_db(config.db_path)

    logger.info("Hole Jobliste...")
    raw_jobs = fetch_job_list(config.arbeitsamt)
    logger.info("%d Jobs gefunden", len(raw_jobs))

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

        job = build_job(raw)
        if job is None:
            failed += 1
            continue

        result = analyze(job.raw_text or "", api_key=config.anthropic_api_key)

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

    logger.info(
        "Fertig. Neu: %d, Übersprungen: %d, Re-analysiert: %d, Fehlgeschlagen: %d",
        new, skipped, reanalyzed, failed,
    )


if __name__ == "__main__":
    run()
