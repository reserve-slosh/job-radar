import logging
import time
import requests
from bs4 import BeautifulSoup
from job_radar.config import ArbeitsamtConfig, SearchProfile

logger = logging.getLogger(__name__)

DETAIL_BASE_URL = "https://www.arbeitsagentur.de/jobsuche/jobdetail"


def fetch_job_list(config: ArbeitsamtConfig, search_profile: SearchProfile) -> list[dict]:
    """Holt die Suchergebnisse von der Such-API für alle konfigurierten Queries."""
    queries = search_profile.get_arbeitsagentur_queries()
    if not queries:
        logger.warning("Keine arbeitsagentur_queries konfiguriert — überspringe Arbeitsagentur-Abfrage.")
        return []

    url = f"{config.base_url}/jobs"
    headers = {"X-API-Key": config.api_key}
    collected: dict[str, dict] = {}

    for query in queries:
        was = query.get("was", "")
        for page in range(1, config.max_pages + 1):
            try:
                response = requests.get(
                    url, headers=headers, params={**query, "page": page}, timeout=10
                )
                response.raise_for_status()
                jobs = response.json().get("stellenangebote", [])
            except requests.RequestException as e:
                logger.error("Fehler bei Query '%s' Seite %d: %s", was, page, e)
                break

            logger.debug("AA query '%s' Seite %d — %d Ergebnisse", was, page, len(jobs))
            time.sleep(1)

            if not jobs:
                break

            for job in jobs:
                refnr = job.get("refnr")
                if refnr:
                    collected[refnr] = job

    results = list(collected.values())
    logger.info("Arbeitsagentur: %d eindeutige Jobs gesammelt", len(results))
    return results


def fetch_job_detail(refnr: str) -> str | None:
    """Holt den Rohtext der Detailseite für eine gegebene refnr."""
    url = f"{DETAIL_BASE_URL}/{refnr}"

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return _extract_text(response.text)
    except requests.RequestException as e:
        logger.error("Fehler beim Abrufen von %s: %s", refnr, e)
        return None


def _extract_text(html: str) -> str:
    """Extrahiert den relevanten Textinhalt aus dem HTML."""
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "nav", "header", "footer"]):
        tag.decompose()

    main = soup.find("main") or soup.find("body")
    if main is None:
        return ""

    return " ".join(main.get_text(separator=" ").split())