import pytest
from unittest.mock import patch

from job_radar.pipeline.extractor import build_job

DETAIL_TEXT = "Das ist der Stellentext."


@pytest.fixture(autouse=True)
def mock_fetch_detail():
    with patch(
        "job_radar.pipeline.extractor.fetch_job_detail", return_value=DETAIL_TEXT
    ):
        yield


def _raw(**overrides) -> dict:
    base = {
        "refnr": "DE-1234-5678",
        "titel": "Data Engineer",
        "arbeitgeber": "Acme GmbH",
        "arbeitsort": {"ort": "Köln"},
        "eintrittsdatum": "2026-03-01",
        "aktuelleVeroeffentlichungsdatum": "2026-02-01",
        "modifikationsTimestamp": "2026-02-01T12:00:00",
    }
    base.update(overrides)
    return base


def test_build_job_returns_job_with_correct_fields():
    job = build_job(_raw())

    assert job is not None
    assert job.refnr == "DE-1234-5678"
    assert job.titel == "Data Engineer"
    assert job.arbeitgeber == "Acme GmbH"
    assert job.ort == "Köln"
    assert job.eintrittsdatum == "2026-03-01"
    assert job.veroeffentlicht_am == "2026-02-01"
    assert job.modifikations_timestamp == "2026-02-01T12:00:00"
    assert job.raw_text == DETAIL_TEXT
    assert job.source == "arbeitsagentur"


def test_build_job_returns_none_if_refnr_missing():
    raw = _raw()
    del raw["refnr"]
    assert build_job(raw) is None


def test_build_job_handles_missing_optional_fields():
    job = build_job({"refnr": "DE-9999-0000"})

    assert job is not None
    assert job.titel == ""
    assert job.arbeitgeber == ""
    assert job.ort == ""
    assert job.eintrittsdatum is None
    assert job.veroeffentlicht_am is None
    assert job.modifikations_timestamp is None
