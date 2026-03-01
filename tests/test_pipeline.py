import sys
from pathlib import Path

# run_pipeline.py lives in scripts/, not a package — make it importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import pytest
from unittest.mock import MagicMock, patch

from job_radar.config import CandidateProfile, SearchProfile
from job_radar.db.models import Job
from run_pipeline import _process_batch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_search_profile(**overrides) -> SearchProfile:
    defaults = dict(
        name="koeln",
        remote_only=False,
        location_filter=["Köln"],
        title_keywords=frozenset(["referent"]),
        title_exclude=frozenset(),
        fit_score_context="",
        arbeitsagentur_queries=[],
    )
    defaults.update(overrides)
    return SearchProfile(**defaults)


def _make_candidate(search_profile: SearchProfile) -> CandidateProfile:
    return CandidateProfile(
        name="test",
        profile_text="Test profile",
        search_profiles=[search_profile],
    )


def _make_config(db_path: str) -> MagicMock:
    config = MagicMock()
    config.db_path = db_path
    config.anthropic_api_key = "test-key"
    return config


def _make_job(**overrides) -> Job:
    defaults = dict(
        refnr="AA-001",
        titel="Referent Diversity",
        arbeitgeber="Test GmbH",
        ort="Köln",
        eintrittsdatum=None,
        veroeffentlicht_am=None,
    )
    defaults.update(overrides)
    return Job(**defaults)


def _stub_result() -> dict:
    return {
        "titel_normalisiert": None,
        "remote": None,
        "vertragsart": None,
        "seniority": None,
        "tech_stack": None,
        "zusammenfassung": None,
        "fit_score": None,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_title_mismatch_counted_as_skipped(tmp_path):
    """A job whose title doesn't match any keyword is skipped before build_job."""
    sp = _make_search_profile()
    candidate = _make_candidate(sp)
    config = _make_config(str(tmp_path / "test.db"))
    raw = {"refnr": "AA-001", "titel": "Buchhalter"}  # no match for "referent"

    with patch("run_pipeline.build_job") as mock_build, \
         patch("run_pipeline.job_exists", return_value=False), \
         patch("run_pipeline.analyze"), \
         patch("run_pipeline.insert_job"):

        new, skipped, reanalyzed, failed = _process_batch(
            [raw], "arbeitsagentur", config, candidate, sp
        )

    assert skipped == 1
    assert new == 0
    mock_build.assert_not_called()


def test_title_match_counted_as_new(tmp_path):
    """A matching job that isn't in the DB is inserted and counted as new."""
    sp = _make_search_profile()
    candidate = _make_candidate(sp)
    config = _make_config(str(tmp_path / "test.db"))
    raw = {"refnr": "AA-002", "titel": "Referent Diversity", "modifikationsTimestamp": None}
    job = _make_job(refnr="AA-002")

    with patch("run_pipeline.build_job", return_value=job), \
         patch("run_pipeline.job_exists", return_value=False), \
         patch("run_pipeline.analyze", return_value=_stub_result()), \
         patch("run_pipeline.insert_job"):

        new, skipped, reanalyzed, failed = _process_batch(
            [raw], "arbeitsagentur", config, candidate, sp
        )

    assert new == 1
    assert skipped == 0
    assert failed == 0


def test_no_llm_passes_empty_api_key_and_fit_score_is_none(tmp_path):
    """no_llm=True causes analyze to receive api_key='' and the stored fit_score is None."""
    sp = _make_search_profile()
    candidate = _make_candidate(sp)
    config = _make_config(str(tmp_path / "test.db"))
    raw = {"refnr": "AA-003", "titel": "Referent Diversity", "modifikationsTimestamp": None}
    job = _make_job(refnr="AA-003")

    with patch("run_pipeline.build_job", return_value=job), \
         patch("run_pipeline.job_exists", return_value=False), \
         patch("run_pipeline.analyze", return_value=_stub_result()) as mock_analyze, \
         patch("run_pipeline.insert_job") as mock_insert:

        _process_batch([raw], "arbeitsagentur", config, candidate, sp, no_llm=True)

    assert mock_analyze.call_args.kwargs["api_key"] == ""
    inserted_job = mock_insert.call_args.args[1]
    assert inserted_job.fit_score is None


def test_build_job_none_counted_as_failed(tmp_path):
    """When build_job returns None the job is counted as failed, not skipped or new."""
    sp = _make_search_profile()
    candidate = _make_candidate(sp)
    config = _make_config(str(tmp_path / "test.db"))
    # Use arbeitnow source to bypass the arbeitsagentur-only pre-filter
    raw = {"refnr": "AN-001", "titel": "Referent", "remote": False, "modifikationsTimestamp": None}

    with patch("run_pipeline.build_job", return_value=None), \
         patch("run_pipeline.job_exists", return_value=False), \
         patch("run_pipeline.analyze"), \
         patch("run_pipeline.insert_job"):

        new, skipped, reanalyzed, failed = _process_batch(
            [raw], "arbeitnow", config, candidate, sp
        )

    assert failed == 1
    assert new == 0
    assert skipped == 0
