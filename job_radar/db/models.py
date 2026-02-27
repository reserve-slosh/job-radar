import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime


@dataclass
class Job:
    refnr: str
    titel: str
    arbeitgeber: str
    ort: str
    eintrittsdatum: str | None
    veroeffentlicht_am: str | None
    raw_text: str | None = None
    llm_output: str | None = None
    titel_normalisiert: str | None = None
    remote: str | None = None
    vertragsart: str | None = None
    seniority: str | None = None
    tech_stack: str | None = None  # JSON-String
    zusammenfassung: str | None = None
    fit_score: int | None = None
    modifikations_timestamp: str | None = None
    source: str = "arbeitsagentur"
    fetched_at: str = ""

    def __post_init__(self):
        if not self.fetched_at:
            self.fetched_at = datetime.utcnow().isoformat()


@contextmanager
def get_connection(db_path: str):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: str) -> None:
    with get_connection(db_path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                refnr TEXT PRIMARY KEY,
                titel TEXT NOT NULL,
                arbeitgeber TEXT,
                ort TEXT,
                eintrittsdatum TEXT,
                veroeffentlicht_am TEXT,
                raw_text TEXT,
                llm_output TEXT,
                titel_normalisiert TEXT,
                remote TEXT,
                vertragsart TEXT,
                seniority TEXT,
                tech_stack TEXT,
                zusammenfassung TEXT,
                fit_score INTEGER,
                modifikations_timestamp TEXT,
                source TEXT DEFAULT 'arbeitsagentur',
                fetched_at TEXT
            )
        """)


def get_modifikations_timestamp(db_path: str, refnr: str) -> str | None:
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT modifikations_timestamp FROM jobs WHERE refnr = ?", (refnr,)
        ).fetchone()
        return row["modifikations_timestamp"] if row else None


def job_exists(db_path: str, refnr: str) -> bool:
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT 1 FROM jobs WHERE refnr = ?", (refnr,)
        ).fetchone()
        return row is not None


def insert_job(db_path: str, job: Job) -> None:
    with get_connection(db_path) as conn:
        conn.execute("""
            INSERT INTO jobs (
                refnr, titel, arbeitgeber, ort, eintrittsdatum,
                veroeffentlicht_am, raw_text, llm_output, titel_normalisiert,
                remote, vertragsart, seniority, tech_stack, zusammenfassung,
                fit_score, modifikations_timestamp, source, fetched_at
            ) VALUES (
                :refnr, :titel, :arbeitgeber, :ort, :eintrittsdatum,
                :veroeffentlicht_am, :raw_text, :llm_output, :titel_normalisiert,
                :remote, :vertragsart, :seniority, :tech_stack, :zusammenfassung,
                :fit_score, :modifikations_timestamp, :source, :fetched_at
            )
        """, job.__dict__)

def update_job(db_path: str, job: Job) -> None:
    with get_connection(db_path) as conn:
        conn.execute("""
            UPDATE jobs SET
                titel = :titel,
                arbeitgeber = :arbeitgeber,
                ort = :ort,
                eintrittsdatum = :eintrittsdatum,
                veroeffentlicht_am = :veroeffentlicht_am,
                raw_text = :raw_text,
                llm_output = :llm_output,
                titel_normalisiert = :titel_normalisiert,
                remote = :remote,
                vertragsart = :vertragsart,
                seniority = :seniority,
                tech_stack = :tech_stack,
                zusammenfassung = :zusammenfassung,
                fit_score = :fit_score,
                modifikations_timestamp = :modifikations_timestamp,
                fetched_at = :fetched_at
            WHERE refnr = :refnr
        """, job.__dict__)
