import logging
import requests
from bs4 import BeautifulSoup
from job_radar.config import ArbeitsamtConfig

logger = logging.getLogger(__name__)

DETAIL_BASE_URL = "https://www.arbeitsagentur.de/jobsuche/jobdetail"


def fetch_job_list(config: ArbeitsamtConfig) -> list[dict]:
    """Holt die Suchergebnisse von der Such-API."""
    url = f"{config.base_url}/jobs"
    headers = {"X-API-Key": config.api_key}

    try:
        response = requests.get(url, headers=headers, params=config.search_params, timeout=10)
        response.raise_for_status()
        data = response.json()
        return data.get("stellenangebote", [])
    except requests.RequestException as e:
        logger.error("Fehler beim Abrufen der Jobliste: %s", e)
        return []


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
