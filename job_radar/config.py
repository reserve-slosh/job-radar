import re
from dataclasses import dataclass, field
from pathlib import Path
from dotenv import load_dotenv
import os
import yaml

load_dotenv()

_AA_QUERY_DEFAULTS: dict = {
    "angebotsart": 1,
    "arbeitszeit": "vz;tz",
    "size": 25,
}


@dataclass
class SearchProfile:
    name: str
    remote_only: bool
    location_filter: list[str]
    title_keywords: frozenset[str]
    title_exclude: frozenset[str]
    fit_score_context: str = ""
    enabled: bool = True
    arbeitsagentur_queries: list[dict] = field(default_factory=list)

    def get_arbeitsagentur_queries(self) -> list[dict]:
        """Returns merged query dicts: defaults overridden by each entry."""
        return [{**_AA_QUERY_DEFAULTS, **q} for q in self.arbeitsagentur_queries]

    def matches_location(self, job: dict) -> bool:
        """Returns True if the job passes the location filter for this search profile."""
        if job.get("remote") is True:
            return True
        if self.remote_only:
            return False
        ort = job.get("ort") or ""
        return any(term.lower() in ort.lower() for term in self.location_filter)

    def matches_title(self, job: dict) -> bool:
        """Returns True if the job title contains a keyword and no exclude term."""
        title = (job.get("titel") or "").lower()
        # No trailing \b: intentional prefix match (e.g. "referent" matches "Referentin")
        has_keyword = any(
            re.search(r"\b" + re.escape(kw.strip()), title)
            for kw in self.title_keywords
        )
        # Full word boundary for excludes to avoid over-excluding
        is_excluded = any(
            re.search(r"\b" + re.escape(ex.strip()) + r"\b", title)
            for ex in self.title_exclude
        )
        return has_keyword and not is_excluded


@dataclass
class CandidateProfile:
    name: str
    profile_text: str
    search_profiles: list[SearchProfile]


def load_profiles(profiles_dir: str | Path) -> list[CandidateProfile]:
    """Loads all candidate profiles from YAML files in the given directory."""
    profiles_dir = Path(profiles_dir)
    profiles = []
    for path in sorted(profiles_dir.glob("*.yaml")):
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        search_profiles = []
        for sp in data.get("search_profiles", []):
            if "arbeitsagentur_query" in sp:
                raise ValueError(
                    f"Profile '{data['name']}' uses deprecated key 'arbeitsagentur_query' "
                    f"in search profile '{sp['name']}'. Rename it to 'arbeitsagentur_queries' "
                    f"and wrap the value in a list."
                )
            search_profiles.append(SearchProfile(
                name=sp["name"],
                remote_only=sp.get("remote_only", False),
                location_filter=sp.get("location_filter", []),
                title_keywords=frozenset(sp.get("title_keywords", [])),
                title_exclude=frozenset(sp.get("title_exclude", [])),
                fit_score_context=sp.get("fit_score_context", ""),
                enabled=sp.get("enabled", True),
                arbeitsagentur_queries=sp.get("arbeitsagentur_queries", []),
            ))
        profiles.append(CandidateProfile(
            name=data["name"],
            profile_text=data.get("profile_text", ""),
            search_profiles=search_profiles,
        ))
    return profiles


@dataclass
class ArbeitsamtConfig:
    base_url: str = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4"
    api_key: str = "jobboerse-jobsuche"
    max_pages: int = 10


@dataclass
class ArbeitnowConfig:
    base_url: str = "https://www.arbeitnow.com/api/job-board-api"
    max_pages: int = 5


@dataclass
class Config:
    anthropic_api_key: str = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))
    db_path: str = field(default_factory=lambda: os.getenv("DB_PATH", "job_radar.db"))
    profiles_dir: str = field(default_factory=lambda: os.getenv("PROFILES_DIR", "profiles"))
    arbeitsamt: ArbeitsamtConfig = field(default_factory=ArbeitsamtConfig)
    arbeitnow: ArbeitnowConfig = field(default_factory=ArbeitnowConfig)