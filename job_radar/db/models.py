import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
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
    search_profile: str = "koeln"
    fetched_at: str = ""

    def __post_init__(self):
        if not self.fetched_at:
            self.fetched_at = datetime.utcnow().isoformat()


@dataclass
class PipelineRun:
    id: int | None = None
    started_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    finished_at: str | None = None
    source: str = ""
    jobs_fetched: int = 0
    jobs_new: int = 0
    jobs_updated: int = 0
    jobs_skipped: int = 0
    jobs_failed: int = 0
    status: str = "running"
    error_msg: str | None = None


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
                fetched_at TEXT,
                bewerbung_entwurf TEXT,
                bewerbung_status TEXT,
                search_profile TEXT DEFAULT 'koeln'
            )
        """)
        try:
            conn.execute("ALTER TABLE jobs ADD COLUMN bewerbung_entwurf TEXT")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("ALTER TABLE jobs ADD COLUMN bewerbung_status TEXT")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("ALTER TABLE jobs ADD COLUMN search_profile TEXT DEFAULT 'koeln'")
        except sqlite3.OperationalError:
            pass
        conn.execute("""
            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                source TEXT NOT NULL,
                jobs_fetched INTEGER DEFAULT 0,
                jobs_new INTEGER DEFAULT 0,
                jobs_updated INTEGER DEFAULT 0,
                jobs_skipped INTEGER DEFAULT 0,
                jobs_failed INTEGER DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'running',
                error_msg TEXT,
                search_profile TEXT DEFAULT 'koeln'
            )
        """)
        try:
            conn.execute("ALTER TABLE runs ADD COLUMN search_profile TEXT DEFAULT 'koeln'")
        except sqlite3.OperationalError:
            pass
        conn.execute("UPDATE jobs SET search_profile = 'koeln' WHERE search_profile IS NULL")
        conn.execute("UPDATE runs SET search_profile = 'koeln' WHERE search_profile IS NULL")


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


def update_bewerbung(
    db_path: str,
    refnr: str,
    *,
    entwurf: str | None = None,
    status: str | None = None,
) -> None:
    updates: dict[str, str] = {}
    if entwurf is not None:
        updates["bewerbung_entwurf"] = entwurf
    if status is not None:
        updates["bewerbung_status"] = status
    if not updates:
        return
    set_clause = ", ".join(f"{col} = :{col}" for col in updates)
    updates["refnr"] = refnr
    with get_connection(db_path) as conn:
        conn.execute(
            f"UPDATE jobs SET {set_clause} WHERE refnr = :refnr", updates
        )


def insert_run(db_path: str, run: PipelineRun) -> int:
    with get_connection(db_path) as conn:
        cursor = conn.execute("""
            INSERT INTO runs (
                started_at, finished_at, source,
                jobs_fetched, jobs_new, jobs_updated, jobs_skipped,
                status, error_msg
            ) VALUES (
                :started_at, :finished_at, :source,
                :jobs_fetched, :jobs_new, :jobs_updated, :jobs_skipped,
                :status, :error_msg
            )
        """, run.__dict__)
        return cursor.lastrowid


def finish_run(
    db_path: str,
    run_id: int,
    *,
    jobs_fetched: int,
    jobs_new: int,
    jobs_updated: int,
    jobs_skipped: int,
    jobs_failed: int,
    status: str,
    error_msg: str | None = None,
) -> None:
    with get_connection(db_path) as conn:
        conn.execute("""
            UPDATE runs SET
                finished_at = :finished_at,
                jobs_fetched = :jobs_fetched,
                jobs_new = :jobs_new,
                jobs_updated = :jobs_updated,
                jobs_skipped = :jobs_skipped,
                jobs_failed = :jobs_failed,
                status = :status,
                error_msg = :error_msg
            WHERE id = :id
        """, {
            "finished_at": datetime.utcnow().isoformat(),
            "jobs_fetched": jobs_fetched,
            "jobs_new": jobs_new,
            "jobs_updated": jobs_updated,
            "jobs_skipped": jobs_skipped,
            "jobs_failed": jobs_failed,
            "status": status,
            "error_msg": error_msg,
            "id": run_id,
        })
