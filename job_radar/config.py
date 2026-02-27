import re
from dataclasses import dataclass, field
from typing import ClassVar
from dotenv import load_dotenv
import os

load_dotenv()


@dataclass
class ArbeitsamtConfig:
    base_url: str = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4"
    api_key: str = "jobboerse-jobsuche"
    search_params: dict = field(default_factory=lambda: {
        "was": "Data Engineer",
        "wo": "50667",
        "umkreis": 25,
        "angebotsart": 1,
        "arbeitszeit": "vz;tz",
        "size": 25,
    })


@dataclass
class ArbeitnowConfig:
    TITLE_KEYWORDS: ClassVar[frozenset[str]] = frozenset({
        "data", "engineer", "scientist", "analytics", "python",
        "backend", "software", "ml", "ai", "platform",
    })
    TITLE_EXCLUDE: ClassVar[frozenset[str]] = frozenset({
        "head of", "director", "vp ", "chief", "c-level",
    })

    base_url: str = "https://www.arbeitnow.com/api/job-board-api"
    max_pages: int = 5
    location_filter: list = field(default_factory=lambda: [
        "Köln", "Cologne", "Koeln", "50",
    ])

    def matches_location(self, job: dict) -> bool:
        """Returns True if the normalized job dict passes the location filter.

        Passes if remote is True, or if any filter term is a case-insensitive
        substring of job["ort"].
        """
        if job.get("remote") is True:
            return True
        ort = job.get("ort") or ""
        return any(term.lower() in ort.lower() for term in self.location_filter)

    def matches_title(self, job: dict) -> bool:
        """Returns True if the job title contains a keyword and no exclude term.

        Uses word-boundary matching so e.g. 'ai' doesn't match 'email' and
        'ml' doesn't match 'html'.
        """
        title = (job.get("titel") or "").lower()
        has_keyword = any(
            re.search(r"\b" + re.escape(kw.strip()) + r"\b", title)
            for kw in self.TITLE_KEYWORDS
        )
        is_excluded = any(
            re.search(r"\b" + re.escape(ex.strip()) + r"\b", title)
            for ex in self.TITLE_EXCLUDE
        )
        return has_keyword and not is_excluded


@dataclass
class Config:
    anthropic_api_key: str = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))
    db_path: str = field(default_factory=lambda: os.getenv("DB_PATH", "job_radar.db"))
    arbeitsamt: ArbeitsamtConfig = field(default_factory=ArbeitsamtConfig)
    arbeitnow: ArbeitnowConfig = field(default_factory=ArbeitnowConfig)
