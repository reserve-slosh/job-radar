from dataclasses import dataclass, field
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


@dataclass
class Config:
    anthropic_api_key: str = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))
    db_path: str = field(default_factory=lambda: os.getenv("DB_PATH", "job_radar.db"))
    arbeitsamt: ArbeitsamtConfig = field(default_factory=ArbeitsamtConfig)
    arbeitnow: ArbeitnowConfig = field(default_factory=ArbeitnowConfig)
