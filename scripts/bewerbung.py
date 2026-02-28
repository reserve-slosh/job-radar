"""Bewerbungsassistent — generates a LaTeX cover letter draft for a given job.

Usage:
    python scripts/bewerbung.py --refnr <refnr> [--profile profiles/profile.txt]
                                [--template templates/anschreiben_template.tex]
                                [--out output/]
"""

import argparse
import json
import logging
import re
import sys
from datetime import datetime
from pathlib import Path

import anthropic
from dotenv import load_dotenv

from job_radar.config import Config
from job_radar.db.models import get_connection, update_bewerbung

load_dotenv()

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(levelname)s — %(message)s")

_MODEL = "claude-sonnet-4-20250514"
_THINKING_BUDGET = 3000  # Token-Budget für Reasoning
_PLACEHOLDERS = ["BETREFF", "ANREDE", "BODY", "GRUSSFORMEL"]
_LATEX_ESCAPE = {
    "&": r"\&",
    "%": r"\%",
    "_": r"\_",
    "#": r"\#",
    "$": r"\$",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
    "\\": r"\textbackslash{}",
}


def _fetch_job(db_path: str, refnr: str) -> dict:
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT refnr, titel, arbeitgeber, ort, raw_text, zusammenfassung, fit_score "
            "FROM jobs WHERE refnr = ?",
            (refnr,),
        ).fetchone()
    if row is None:
        raise ValueError(f"Job nicht gefunden: {refnr}")
    return dict(row)


def _escape_latex(text: str) -> str:
    return "".join(_LATEX_ESCAPE.get(c, c) for c in text)


def _build_prompt(profile: str, job: dict) -> str:
    job_context = (
        f"Stellentitel: {job['titel']}\n"
        f"Unternehmen: {job['arbeitgeber']}\n"
        f"Ort: {job['ort']}\n\n"
        f"Stellenbeschreibung:\n{job['raw_text'] or job.get('zusammenfassung', '')}"
    )

    return f"""Du schreibst ein Anschreiben für Flemming Reese.

# Kandidatenprofil & Stil-Referenz
{profile}

# Stellenanzeige
{job_context}

# Recherche
Recherchiere das Unternehmen kurz mit Web Search, bevor du schreibst.
Nutze ausschließlich: offizielle Unternehmenswebsite, LinkedIn Company Page, Kununu.
Keine Jobbörsen, keine anonymen Blogs.
Wenn du keine spezifischen, verlässlichen Infos findest: schreib einen kurzen, ehrlichen Satz
statt eines generischen Absatzes. Erfinde nichts.

# Aufgabe
Schreib ein Anschreiben im Stil eines der beiden Referenz-Anschreiben aus dem Profil.

Entscheide zuerst: Welches Referenz-Anschreiben passt besser zur Unternehmenskultur?
- Anschreiben A (Qimia): etablierte Unternehmen, Beratungen, Konzerne, traditionelle Kultur
- Anschreiben B (taod): Startups, moderne Tech-Firmen, Du-Kultur, flache Hierarchien

Orientiere dich eng am gewählten Referenz-Anschreiben: gleiche Satzstruktur, gleiche Rhythmik,
gleiche Art Projekte zu beschreiben. Ersetze nur die unternehmensspezifischen und
jobspezifischen Teile durch passende Inhalte aus der Stellenanzeige und deiner Recherche.

Weitere Regeln:
- Kein Floskeln-Einstieg ("Hiermit bewerbe ich mich", "Mit großem Interesse")
- Jede Aussage hat einen konkreten Beleg oder Kontext
- Lücken im Tech Stack nur nennen wenn sie zentral und prominent in der Stelle sind
- Niemals generische Unternehmenslobby ("technische Tiefe und Kundenorientierung" o.ä.)
- Keine Citation-Tags, keine Quellenverweise im Text — nur plain text
- Länge: 3–4 Absätze, nicht mehr

Antworte ausschließlich mit einem JSON-Objekt, keine Erklärungen, kein Markdown:
{{
  "stil": "A" oder "B",
  "BETREFF_ZUSATZ": "exakte Berufsbezeichnung aus der Anzeige (m/w/d)",
  "ANREDE": "Sehr geehrte Damen und Herren," oder "Hallo [Team/Unternehmen]," je nach Stil,
  "BODY": "vollständiger Fließtext, Absätze mit \\n\\n getrennt",
  "GRUSSFORMEL": "Mit freundlichen Grüßen" oder "Viele Grüße" passend zum Stil
}}"""


def _call_sonnet(prompt: str, api_key: str) -> tuple[dict, list[str]]:
    client = anthropic.Anthropic(api_key=api_key)
    message = client.beta.messages.create(
        model=_MODEL,
        max_tokens=_THINKING_BUDGET + 1500,
        thinking={"type": "enabled", "budget_tokens": _THINKING_BUDGET},
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{"role": "user", "content": prompt}],
        betas=["interleaved-thinking-2025-05-14"],
    )

    text_parts = []
    sources = []

    for block in message.content:
        if block.type == "text":
            text_parts.append(block.text)
        elif block.type == "thinking":
            logger.debug("Thinking: %s", block.thinking[:200])
        elif block.type == "tool_result":
            for item in getattr(block, "content", []):
                url = getattr(item, "url", None)
                if url:
                    sources.append(url)

    raw = " ".join(text_parts).strip()
    raw = re.sub(r"^```json\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw), sources


def _fill_template(template: str, values: dict) -> str:
    augmented = dict(values)
    augmented["BETREFF"] = f"Bewerbung als {values['BETREFF_ZUSATZ']}"

    result = template
    for key in _PLACEHOLDERS:
        value = augmented.get(key, "")
        if key == "BODY":
            escaped = _escape_latex(value) if value else ""
        else:
            escaped = _escape_latex(value) if value else ""
        result = result.replace(f"{{{{{key}}}}}", escaped)
    return result


def _write_output(
    tex: str, out_dir: Path, arbeitgeber: str, sources: list[str]
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^\w]", "_", arbeitgeber.lower())[:30]
    date = datetime.now().strftime("%Y%m%d")
    filename = f"anschreiben_{slug}_{date}.tex"
    path = out_dir / filename

    if sources:
        source_block = "\n% Quellen (Web Search):\n" + "".join(
            f"% - {url}\n" for url in sources
        )
        tex = tex.replace(r"\end{document}", source_block + r"\end{document}")

    path.write_text(tex, encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Anschreiben-Entwurf erstellen")
    parser.add_argument("--refnr", required=True, help="Job-Referenznummer aus der DB")
    parser.add_argument(
        "--profile",
        default="profiles/profile.txt",
        help="Pfad zur Kandidatenprofil-Datei (default: profiles/profile.txt)",
    )
    parser.add_argument(
        "--template",
        default="templates/anschreiben_template.tex",
        help="Pfad zum LaTeX-Template (default: templates/anschreiben_template.tex)",
    )
    parser.add_argument(
        "--out",
        default="output/bewerbungen",
        help="Ausgabeverzeichnis (default: output/bewerbungen)",
    )
    args = parser.parse_args()

    config = Config()

    profile_path = Path(args.profile)
    template_path = Path(args.template)
    if not profile_path.exists():
        logger.error("Profil-Datei nicht gefunden: %s", profile_path)
        sys.exit(1)
    if not template_path.exists():
        logger.error("Template nicht gefunden: %s", template_path)
        sys.exit(1)

    profile = profile_path.read_text(encoding="utf-8")
    template = template_path.read_text(encoding="utf-8")

    logger.info("Lade Job: %s", args.refnr)
    try:
        job = _fetch_job(config.db_path, args.refnr)
    except ValueError as e:
        logger.error("%s", e)
        sys.exit(1)
    logger.info("Job: %s @ %s", job["titel"], job["arbeitgeber"])

    logger.info("Rufe Sonnet auf (inkl. Web Search)...")
    prompt = _build_prompt(profile, job)
    values, sources = _call_sonnet(prompt, config.anthropic_api_key)

    logger.info("Stil gewählt: Anschreiben %s", values.get("stil", "?"))
    if sources:
        logger.info("Web Search Quellen: %s", sources)

    tex = _fill_template(template, values)
    out_path = _write_output(tex, Path(args.out), job["arbeitgeber"], sources)
    logger.info("Entwurf gespeichert: %s", out_path)

    update_bewerbung(config.db_path, args.refnr, entwurf=tex, status="entwurf")
    logger.info("bewerbung_status auf 'entwurf' gesetzt")


if __name__ == "__main__":
    main()
