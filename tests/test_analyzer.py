import json
from unittest.mock import MagicMock, patch

from job_radar.pipeline.analyzer import analyze

_STUB_KEYS = {
    "titel_normalisiert",
    "remote",
    "vertragsart",
    "seniority",
    "tech_stack",
    "zusammenfassung",
    "fit_score",
}

_VALID_RESPONSE = {
    "titel_normalisiert": "Data Engineer",
    "remote": "hybrid",
    "vertragsart": "festanstellung",
    "seniority": "mid",
    "tech_stack": ["Python", "SQL", "Docker"],
    "zusammenfassung": "Interessante Stelle im Data-Engineering-Umfeld.",
    "fit_score": 4,
}

_PROFILE_TEXT = "Kandidat mit Python- und SQL-Kenntnissen."
_FIT_SCORE_CONTEXT = "Bevorzugt Köln/hybrid."


def _mock_anthropic(response_text: str) -> MagicMock:
    """Build a minimal anthropic module mock that returns response_text."""
    mock_message = MagicMock()
    mock_message.content[0].text = response_text

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_message

    mock_anthropic = MagicMock()
    mock_anthropic.Anthropic.return_value = mock_client
    return mock_anthropic


# --- stub fallback ---

def test_analyze_returns_stub_when_no_api_key():
    result = analyze("some text", api_key="")
    assert set(result.keys()) == _STUB_KEYS
    assert all(v is None for v in result.values())


# --- markdown stripping ---

def test_analyze_strips_markdown_codeblock():
    wrapped = f"```json\n{json.dumps(_VALID_RESPONSE)}\n```"
    mock_anthropic = _mock_anthropic(wrapped)

    with patch.dict("sys.modules", {"anthropic": mock_anthropic}):
        result = analyze(
            "some text",
            api_key="test-key",
            profile_text=_PROFILE_TEXT,
            fit_score_context=_FIT_SCORE_CONTEXT,
        )

    assert result["fit_score"] == _VALID_RESPONSE["fit_score"]
    assert result["remote"] == _VALID_RESPONSE["remote"]


# --- plain JSON response ---

def test_analyze_parses_plain_json_response():
    mock_anthropic = _mock_anthropic(json.dumps(_VALID_RESPONSE))

    with patch.dict("sys.modules", {"anthropic": mock_anthropic}):
        result = analyze(
            "some text",
            api_key="test-key",
            profile_text=_PROFILE_TEXT,
            fit_score_context=_FIT_SCORE_CONTEXT,
        )

    assert set(result.keys()) == _STUB_KEYS
    assert result["titel_normalisiert"] == "Data Engineer"
    assert result["seniority"] == "mid"
    assert result["tech_stack"] == ["Python", "SQL", "Docker"]
    assert result["fit_score"] == 4


# --- profile_text is passed through to the prompt ---

def test_analyze_includes_profile_text_in_prompt():
    mock_anthropic = _mock_anthropic(json.dumps(_VALID_RESPONSE))

    with patch.dict("sys.modules", {"anthropic": mock_anthropic}):
        analyze(
            "some text",
            api_key="test-key",
            profile_text=_PROFILE_TEXT,
            fit_score_context=_FIT_SCORE_CONTEXT,
        )

    call_args = mock_anthropic.Anthropic.return_value.messages.create.call_args
    prompt = call_args.kwargs["messages"][0]["content"]
    assert _PROFILE_TEXT in prompt
    assert _FIT_SCORE_CONTEXT in prompt
