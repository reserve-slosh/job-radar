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
class Config:
    anthropic_api_key: str = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))
    db_path: str = field(default_factory=lambda: os.getenv("DB_PATH", "job_radar.db"))
    arbeitsamt: ArbeitsamtConfig = field(default_factory=ArbeitsamtConfig)
