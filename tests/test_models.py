import sqlite3
import pytest

from job_radar.db.models import (
    Job,
    get_modifikations_timestamp,
    init_db,
    insert_job,
    job_exists,
    update_job,
)


@pytest.fixture
def db(tmp_path):
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    return db_path


def _make_job(**overrides) -> Job:
    defaults = dict(
        refnr="DE-1234-5678",
        titel="Data Engineer",
        arbeitgeber="Acme GmbH",
        ort="Köln",
        eintrittsdatum="2026-03-01",
        veroeffentlicht_am="2026-02-01",
        raw_text="Stellentext",
        modifikations_timestamp="2026-02-01T12:00:00",
    )
    defaults.update(overrides)
    return Job(**defaults)


# --- init_db ---

def test_init_db_creates_jobs_table(db):
    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='jobs'"
    ).fetchone()
    conn.close()
    assert row is not None


# --- job_exists ---

def test_job_exists_false_for_unknown(db):
    assert job_exists(db, "UNKNOWN") is False


def test_job_exists_true_after_insert(db):
    job = _make_job()
    insert_job(db, job)
    assert job_exists(db, job.refnr) is True


# --- insert_job ---

def test_insert_job_persists_all_fields(db):
    job = _make_job(
        llm_output='{"fit_score": 4}',
        titel_normalisiert="Data Engineer",
        remote="hybrid",
        vertragsart="festanstellung",
        seniority="mid",
        tech_stack='["Python", "SQL"]',
        zusammenfassung="Interessante Stelle.",
        fit_score=4,
    )
    insert_job(db, job)

    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM jobs WHERE refnr = ?", (job.refnr,)).fetchone()
    conn.close()

    assert row["refnr"] == job.refnr
    assert row["titel"] == job.titel
    assert row["arbeitgeber"] == job.arbeitgeber
    assert row["ort"] == job.ort
    assert row["eintrittsdatum"] == job.eintrittsdatum
    assert row["veroeffentlicht_am"] == job.veroeffentlicht_am
    assert row["raw_text"] == job.raw_text
    assert row["llm_output"] == job.llm_output
    assert row["titel_normalisiert"] == job.titel_normalisiert
    assert row["remote"] == job.remote
    assert row["vertragsart"] == job.vertragsart
    assert row["seniority"] == job.seniority
    assert row["tech_stack"] == job.tech_stack
    assert row["zusammenfassung"] == job.zusammenfassung
    assert row["fit_score"] == job.fit_score
    assert row["modifikations_timestamp"] == job.modifikations_timestamp
    assert row["source"] == job.source


# --- update_job ---

def test_update_job_updates_fields(db):
    job = _make_job(seniority="junior", fit_score=2)
    insert_job(db, job)

    job.seniority = "senior"
    job.fit_score = 5
    update_job(db, job)

    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT seniority, fit_score FROM jobs WHERE refnr = ?", (job.refnr,)
    ).fetchone()
    conn.close()

    assert row["seniority"] == "senior"
    assert row["fit_score"] == 5


# --- get_modifikations_timestamp ---

def test_get_modifikations_timestamp_returns_correct_value(db):
    ts = "2026-02-15T08:30:00"
    insert_job(db, _make_job(modifikations_timestamp=ts))
    assert get_modifikations_timestamp(db, "DE-1234-5678") == ts


def test_get_modifikations_timestamp_returns_none_for_unknown(db):
    assert get_modifikations_timestamp(db, "UNKNOWN") is None
