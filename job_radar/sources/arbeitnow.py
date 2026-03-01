import logging
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

from job_radar.config import ArbeitnowConfig, SearchProfile

logger = logging.getLogger(__name__)


def fetch_job_list(config: ArbeitnowConfig, search_profile: SearchProfile) -> list[dict]:
    """Fetches and filters job listings from the Arbeitnow API.

    Filtering is delegated to the SearchProfile so that location and title
    criteria are profile-specific rather than hardcoded in the source.
    """
    location_matched: list[dict] = []

    for page in range(1, config.max_pages + 1):
        jobs = _fetch_page(config.base_url, page)
        if not jobs:
            logger.info("Arbeitnow: keine weiteren Ergebnisse auf Seite %d", page)
            break

        for job in jobs:
            normalized = _normalize(job)
            if search_profile.matches_location(normalized):
                location_matched.append(normalized)

        logger.info("Arbeitnow: Seite %d — %d Jobs geladen", page, len(jobs))

    results = [job for job in location_matched if search_profile.matches_title(job)]
    dropped = len(location_matched) - len(results)
    if dropped:
        logger.info("Arbeitnow: %d Jobs durch Titel-Filter entfernt", dropped)
    logger.info("Arbeitnow: %d Jobs nach allen Filtern", len(results))
    return results


def _fetch_page(base_url: str, page: int) -> list[dict]:
    """Fetches a single page from the API. Returns an empty list on error."""
    try:
        response = requests.get(base_url, params={"page": page}, timeout=10)
        response.raise_for_status()
        return response.json().get("data", [])
    except requests.RequestException as e:
        logger.error("Arbeitnow: Fehler beim Abrufen von Seite %d: %s", page, e)
        return []


def _normalize(job: dict) -> dict:
    """Maps an Arbeitnow job dict to the shared pipeline field schema."""
    return {
        "refnr": job["slug"],
        "titel": job.get("title", ""),
        "arbeitgeber": job.get("company_name", ""),
        "ort": job.get("location", ""),
        "eintrittsdatum": None,
        "aktuelleVeroeffentlichungsdatum": _parse_date(job.get("created_at")),
        "modifikationsTimestamp": None,
        "raw_text": _strip_html(job.get("description", "")),
        "remote": job.get("remote", False),
    }


def _parse_date(created_at: int | None) -> str | None:
    """Converts a Unix timestamp to an ISO date string (YYYY-MM-DD)."""
    if created_at is None:
        return None
    try:
        return datetime.fromtimestamp(created_at, tz=timezone.utc).strftime("%Y-%m-%d")
    except (OSError, OverflowError, ValueError) as e:
        logger.warning("Arbeitnow: ungültiger created_at-Wert %r: %s", created_at, e)
        return None


def _strip_html(html: str) -> str:
    """Strips HTML tags and normalises whitespace."""
    return " ".join(BeautifulSoup(html, "html.parser").get_text(separator=" ").split())
