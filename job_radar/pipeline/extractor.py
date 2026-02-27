import logging
from job_radar.db.models import Job
from job_radar.sources.arbeitsagentur import fetch_job_detail

logger = logging.getLogger(__name__)


def build_job(raw: dict, source: str = "arbeitsagentur") -> Job | None:
    """Baut ein Job-Objekt aus dem API-Response-Dict."""
    try:
        refnr = raw["refnr"]
        arbeitsort = raw.get("arbeitsort", {})

        raw_text = fetch_job_detail(refnr)
        if raw_text is None:
            logger.warning("Kein Detail-Text für %s", refnr)

        return Job(
            refnr=refnr,
            titel=raw.get("titel", ""),
            arbeitgeber=raw.get("arbeitgeber", ""),
            ort=arbeitsort.get("ort", ""),
            eintrittsdatum=raw.get("eintrittsdatum"),
            veroeffentlicht_am=raw.get("aktuelleVeroeffentlichungsdatum"),
            raw_text=raw_text,
            modifikations_timestamp=raw.get("modifikationsTimestamp"),
            source=source,
        )
    except KeyError as e:
        logger.error("Fehlendes Pflichtfeld im API-Response: %s", e)
        return None
