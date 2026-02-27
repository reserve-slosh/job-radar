import logging
import json
from job_radar.config import Config
from job_radar.db.models import init_db, job_exists, insert_job, update_job, get_modifikations_timestamp
from job_radar.sources.arbeitsagentur import fetch_job_list
from job_radar.pipeline.extractor import build_job
from job_radar.pipeline.analyzer import analyze

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


def run():
    config = Config()
    init_db(config.db_path)

    logger.info("Hole Jobliste...")
    raw_jobs = fetch_job_list(config.arbeitsamt)
    logger.info("%d Jobs gefunden", len(raw_jobs))

    new, skipped = 0, 0
    for raw in raw_jobs:
        refnr = raw.get("refnr")
        if not refnr:
            continue

        incoming_ts = raw.get("modifikationsTimestamp")
        if job_exists(config.db_path, refnr):
            stored_ts = get_modifikations_timestamp(config.db_path, refnr)
            if stored_ts == incoming_ts:
                logger.debug("Übersprungen (unverändert): %s", refnr)
                skipped += 1
                continue
            logger.info("Geändert, re-analysiere: %s", refnr)

        job = build_job(raw)
        if job is None:
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

        if job_exists(config.db_path, refnr):
            update_job(config.db_path, job)
            logger.info("Aktualisiert: %s — %s", refnr, job.titel)
        else:
            insert_job(config.db_path, job)
            logger.info("Neu gespeichert: %s — %s", refnr, job.titel)
            new += 1

    logger.info("Fertig. Neu: %d, Übersprungen: %d", new, skipped)


if __name__ == "__main__":
    run()
