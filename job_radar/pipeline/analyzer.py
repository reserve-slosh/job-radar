import json
import logging

logger = logging.getLogger(__name__)

_PROMPT_TEMPLATE = """\
Du analysierst eine Stellenanzeige für einen Kandidaten im Bereich Data Engineering / Data Science.
Extrahiere die folgenden Informationen und antworte ausschließlich mit einem JSON-Objekt, ohne weiteren Text.

Stellenanzeige:
{text}

Antworte mit diesem Schema:
{{
    "titel_normalisiert": "einheitlicher Jobtitel z.B. 'Data Engineer' oder 'Senior Data Scientist'",
    "remote": "remote | hybrid | onsite | unknown",
    "vertragsart": "festanstellung | freelance | praktikum | unknown",
    "seniority": "junior | mid | senior | lead | unknown",
    "tech_stack": ["list", "of", "technologies"],
    "zusammenfassung": "2-3 Sätze Zusammenfassung der Stelle",
    "fit_score": 1
}}

Bewerte fit_score (1–5) anhand dieses Kandidatenprofils:

{profile_text}

{fit_score_context}
"""


def analyze(text: str, api_key: str = "", profile_text: str = "", fit_score_context: str = "") -> dict:
    """Analysiert einen Stellentext via LLM. Fällt auf Stub zurück wenn kein API-Key."""
    if not api_key:
        logger.warning("Kein API-Key gesetzt, verwende Stub.")
        return _stub()

    prompt = _PROMPT_TEMPLATE.format(
        text=text,
        profile_text=profile_text,
        fit_score_context=fit_score_context,
    )

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        return json.loads(raw)
    except Exception as e:
        logger.error("LLM-Analyse fehlgeschlagen: %s", e)
        return _stub()


def _stub() -> dict:
    return {
        "titel_normalisiert": None,
        "remote": None,
        "vertragsart": None,
        "seniority": None,
        "tech_stack": None,
        "zusammenfassung": None,
        "fit_score": None,
    }
