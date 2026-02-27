import json
import logging

logger = logging.getLogger(__name__)

PROMPT_TEMPLATE = """Du analysierst eine Stellenanzeige für einen Data Engineer / Data Scientist.
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

fit_score Skala (1-5) bezogen auf dieses Profil:
- M.Sc. Data Science, Schwerpunkt Data Engineering
- Python, SQL, Docker, Google Cloud, ETL-Pipelines, Linux
- Sucht Festanstellung oder Freelance in Köln / remote
- 1 = sehr unpassend, 5 = sehr passend
"""


def analyze(text: str, api_key: str = "") -> dict:
    """Analysiert einen Stellentext via LLM. Fällt auf Stub zurück wenn kein API-Key."""
    if not api_key:
        logger.warning("Kein API-Key gesetzt, verwende Stub.")
        return _stub()

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=1024,
            messages=[{"role": "user", "content": PROMPT_TEMPLATE.format(text=text)}],
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
