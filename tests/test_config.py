import pytest
from job_radar.config import SearchProfile


def _make_profile(**overrides) -> SearchProfile:
    defaults = dict(
        name="test",
        remote_only=False,
        location_filter=["Köln"],
        title_keywords=frozenset(["referent", "diversity"]),
        title_exclude=frozenset(["head of"]),
        fit_score_context="",
        arbeitsagentur_queries=[],
    )
    defaults.update(overrides)
    return SearchProfile(**defaults)


# ---------------------------------------------------------------------------
# matches_title
# ---------------------------------------------------------------------------

def test_matches_title_exact_word():
    sp = _make_profile()
    assert sp.matches_title({"titel": "Referent Bildung"}) is True


def test_matches_title_prefix_match():
    sp = _make_profile(title_keywords=frozenset(["referent"]))
    assert sp.matches_title({"titel": "Referentin für Gleichstellung"}) is True


def test_matches_title_no_match():
    sp = _make_profile(title_keywords=frozenset(["diversity"]))
    assert sp.matches_title({"titel": "Senior Data Engineer"}) is False


def test_matches_title_exclude_wins():
    sp = _make_profile(
        title_keywords=frozenset(["referent"]),
        title_exclude=frozenset(["head of"]),
    )
    assert sp.matches_title({"titel": "Head of Referenten"}) is False


def test_matches_title_case_insensitive_lower():
    sp = _make_profile(title_keywords=frozenset(["diversity"]))
    assert sp.matches_title({"titel": "Diversity Manager"}) is True


def test_matches_title_case_insensitive_upper():
    sp = _make_profile(title_keywords=frozenset(["diversity"]))
    assert sp.matches_title({"titel": "DIVERSITY LEAD"}) is True


# ---------------------------------------------------------------------------
# matches_location
# ---------------------------------------------------------------------------

def test_matches_location_remote_always_passes_non_remote_profile():
    sp = _make_profile(remote_only=False, location_filter=["Köln"])
    assert sp.matches_location({"ort": "Berlin", "remote": True}) is True


def test_matches_location_remote_only_non_remote_job_fails():
    sp = _make_profile(remote_only=True, location_filter=[])
    assert sp.matches_location({"ort": "Köln", "remote": False}) is False


def test_matches_location_remote_only_remote_job_passes():
    sp = _make_profile(remote_only=True, location_filter=[])
    assert sp.matches_location({"ort": "", "remote": True}) is True


def test_matches_location_ort_match():
    sp = _make_profile(remote_only=False, location_filter=["Köln"])
    assert sp.matches_location({"ort": "Köln, NRW", "remote": False}) is True


def test_matches_location_ort_no_match():
    sp = _make_profile(remote_only=False, location_filter=["Köln"])
    assert sp.matches_location({"ort": "Berlin", "remote": False}) is False


# ---------------------------------------------------------------------------
# get_arbeitsagentur_queries
# ---------------------------------------------------------------------------

def test_get_arbeitsagentur_queries_merges_defaults():
    sp = _make_profile(arbeitsagentur_queries=[{"was": "Referent", "wo": "50667"}])
    queries = sp.get_arbeitsagentur_queries()
    assert len(queries) == 1
    assert queries[0]["angebotsart"] == 1
    assert queries[0]["arbeitszeit"] == "vz;tz"
    assert queries[0]["size"] == 25
    assert queries[0]["was"] == "Referent"


def test_get_arbeitsagentur_queries_profile_overrides_defaults():
    sp = _make_profile(arbeitsagentur_queries=[{"was": "Diversity", "size": 50}])
    queries = sp.get_arbeitsagentur_queries()
    assert queries[0]["size"] == 50
    assert queries[0]["was"] == "Diversity"
    assert queries[0]["angebotsart"] == 1  # default still present


def test_get_arbeitsagentur_queries_multiple_each_get_defaults():
    sp = _make_profile(arbeitsagentur_queries=[
        {"was": "Referent"},
        {"was": "Diversity", "wo": "50667"},
    ])
    queries = sp.get_arbeitsagentur_queries()
    assert len(queries) == 2
    for q in queries:
        assert "angebotsart" in q
        assert "arbeitszeit" in q
        assert "size" in q


def test_get_arbeitsagentur_queries_empty_returns_empty():
    sp = _make_profile(arbeitsagentur_queries=[])
    assert sp.get_arbeitsagentur_queries() == []
