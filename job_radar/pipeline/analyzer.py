import json
import logging

logger = logging.getLogger(__name__)

PROMPT_TEMPLATE = """Du analysierst eine Stellenanzeige für einen Junior Data Engineer / Data Scientist.
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

Erfahrung:
- M.Sc. Data Science (HAW Kiel, 02/2025, Note 1,7); Schwerpunkte: Data Management, Cloud Computing, Big Data Technologies (alle 1,0)
- ~1,5 Jahre als Data Scientist am GEOMAR (Automatisierung, Benchmarking, Python-Pipelines)
- Freiberuflich: End-to-End Datenpipeline für Medienunternehmen (Scraping, Normalisierung, Deduplizierung, MySQL, Docker, Google Cloud, Hetzner-Linux-Server)
- Masterarbeit: modulares Python-Package (src-Layout, pytest, mehrere Solver-Familien) für AUV-Routenoptimierung
- Noch keine Vollzeit-Festanstellung; alle Erfahrung parallel zum Studium

Stack (produktiv eingesetzt):
- Python (stark): Pandas, NumPy, Requests/BeautifulSoup, SQLAlchemy, Matplotlib
- Data Engineering: ETL/ELT, MySQL, Docker, Google Cloud, Linux (Ubuntu), Git
- Software Engineering: modulare Paketarchitektur, pytest, LLM-assisted development
- SQL: mid-level
- Scikit-Learn, FastAPI/Flask, PyTorch: Grundlagen

Keine Produktionserfahrung mit: Spark, Kafka, Airflow, dbt — Konzepte bekannt

Präferenzen:
- Standort Köln; Hybrid oder Onsite bevorzugt, reines Remote eher unerwünscht
- Festanstellung oder Freelance
- Data Engineering Fokus bevorzugt; DS/ML-Anteile in Ordnung; Deep Learning eher unpassend
- Zeitarbeit / Personalvermittler (z.B. FERCHAU, Hays, Gulp) negativ bewerten
- Deutsch oder Englisch beide okay

Scoring-Leitfaden:
5 = DE-Rolle, Stack passt stark (Python, SQL, Docker, Cloud, Linux), Köln/hybrid, Direktanstellung
4 = passt gut, kleinere Lücken im Stack oder leicht erhöhte Seniority-Erwartung
3 = grundsätzlich passend aber nennenswerte Lücken (z.B. Spark-heavy, viel DL) oder Zeitarbeit
2 = eher unpassend (falscher Stack, reines ML/DL, reines Remote, sehr hohe Seniority)
1 = nicht passend (komplett anderes Feld, nur Senior+, nur DL)
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
