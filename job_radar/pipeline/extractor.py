import logging
from job_radar.db.models import Job
from job_radar.sources.arbeitsagentur import fetch_job_detail

logger = logging.getLogger(__name__)


def build_job(raw: dict, source: str = "arbeitsagentur", remote_hint: bool = False) -> Job | None:
    """Baut ein Job-Objekt aus dem API-Response-Dict.

    remote_hint: if True and the LLM remote field is not yet set, marks the job as "remote"
    so that matches_location works correctly before LLM analysis runs (e.g. for arbeitnow
    jobs that carry a remote bool in their normalized dict).
    """
    try:
        refnr = raw["refnr"]
        arbeitsort = raw.get("arbeitsort", {})
        ort = arbeitsort.get("ort") or raw.get("ort", "")

        raw_text = raw.get("raw_text") or fetch_job_detail(refnr)
        if raw_text is None:
            logger.warning("Kein Detail-Text für %s", refnr)

        job = Job(
            refnr=refnr,
            titel=raw.get("titel", ""),
            arbeitgeber=raw.get("arbeitgeber", ""),
            ort=ort,
            eintrittsdatum=raw.get("eintrittsdatum"),
            veroeffentlicht_am=raw.get("aktuelleVeroeffentlichungsdatum"),
            raw_text=raw_text,
            modifikations_timestamp=raw.get("modifikationsTimestamp"),
            source=source,
        )
        if remote_hint and job.remote is None:
            job.remote = "remote"
        return job
    except KeyError as e:
        logger.error("Fehlendes Pflichtfeld im API-Response: %s", e)
        return None
