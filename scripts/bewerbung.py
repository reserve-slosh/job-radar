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
from rich.console import Console
from rich.table import Table

from job_radar.config import Config
from job_radar.db.models import get_connection, update_bewerbung

load_dotenv()

logger = logging.getLogger(__name__)

_MODEL = "claude-sonnet-4-20250514"
_THINKING_BUDGET = 10000  # Token-Budget für Reasoning
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

---

Arbeite die folgenden drei Phasen strikt in dieser Reihenfolge ab.
Das Ergebnis jeder Phase fließt in die nächste ein.

---

## Phase 1: Recherche

Führe mehrere gezielte Web Searches durch. Suche nicht nur die erste offensichtliche Quelle —
plane deine Searches bewusst und priorisiere nach folgendem Schema:

1. **Unternehmenskultur und Arbeitsweise** (Kununu, "Über uns", Karriereseite, Glassdoor)
   Ziel: Gibt es konkrete Aussagen zu Teamstruktur, Arbeitsweise, Werten — jenseits von Marketing?
   Wertlos: "Wir sind ein innovatives Unternehmen", "Work-Life-Balance ist uns wichtig"

2. **Tech Stack und Engineering-Praxis** (Engineering Blog, GitHub, Konferenzauftritte, Stellenanzeigen)
   Ziel: Welche Technologien werden produktiv eingesetzt? Gibt es öffentliche technische Inhalte?

3. **Marktpositionierung** (Website, LinkedIn, Pressemitteilungen, Branchen-Coverage)
   Ziel: Was unterscheidet dieses Unternehmen konkret von vergleichbaren Firmen in dieser Nische?
   Wertlos: Unternehmensgröße, Gründungsjahr, allgemeine Branchenzugehörigkeit

Wenn eine Kategorie nichts Verwertbares liefert: notiere das explizit. Nicht auffüllen.

---

## Phase 2: Analyse

Entscheide auf Basis der Recherche und der Stellenanzeige:

- **unternehmens_differenziator**: Was macht dieses Unternehmen und diese Stelle konkret anders
  als eine vergleichbare Stelle bei einem anderen Arbeitgeber? Ein Satz, der *nur hier* gilt.
  Wenn du das nicht belegen kannst: Wert = null.

- **unternehmens_satz**: Der Satz der im Anschreiben verwendet wird um den Unternehmensbezug
  herzustellen. Muss aus der Recherche ableitbar sein — keine Unternehmenslobby, keine
  generischen Attribute. Wenn kein belegbarer Satz möglich ist: Wert = null, kein
  Unternehmensabsatz im Brief.

- **gewaehlte_erfahrungen**: Wähle 1–2 der folgenden Erfahrungen aus die für diese Stelle
  am stärksten relevant sind. Die anderen fallen weg oder werden maximal in einem Nebensatz erwähnt:
  - "pipeline": Freiberufliches Datenpipeline-Projekt (Scraping, ETL, Docker, Google Cloud)
  - "geomar": GEOMAR (Automatisierung, Benchmarking, interdisziplinäre Kommunikation)
  - "thesis": Masterarbeit (modulares Python-Package, Routenoptimierung, Testsuite)

- **weggelassen**: Welche Erfahrung wurde weggelassen und warum?

- **stil**: "A" (Qimia — formal, Sie-Form, konservativ) oder "B" (taod — locker, Du-Form, Startup)
  Entscheide nach Unternehmenskultur aus der Recherche.
  Faustregel: Beratungsunternehmen, AGs, Konzerne, etablierte Mittelständler → Stil A.
  Stil B nur wenn die Recherche explizit auf flache Hierarchien, Du-Kultur oder Startup-Umfeld hinweist.

- **stil_begruendung**: Ein Satz warum.

---

## Phase 3: Anschreiben schreiben

Schreib das Anschreiben auf Basis von Phase 1 und Phase 2.

**Stil:**
Orientiere dich am gewählten Referenz-Anschreiben (A oder B) aus dem Kandidatenprofil:
gleiche Satzstruktur, gleiche Rhythmik, gleiche Art Projekte zu beschreiben.
Ersetze nur die stellen- und unternehmensspezifischen Teile.

**Tonalität:**
Lies jeden Satz mit dieser Frage: "Könnte dieser Satz in jeder Bewerbung stehen?"
Wenn ja — schreib ihn um bis er nur hier passt, oder streiche ihn.
Keine Konjunktiv-Weichspüler ("könnte", "würde", "wäre").

**Verbotene Phrasen und Muster** (wörtlich oder sinngemäß):
- "technische Exzellenz und Kundenorientierung" oder ähnliche Doppel-Attribute
- "die Brücke zwischen Technik und Fachlichkeit schlagen"
- "ich bin überzeugt, dass ich mich schnell in jeden Stack einarbeiten kann"
- "ob als direkter Einstieg oder im Rahmen von..."
- "intrinsisch motiviert" / "intrinsisch motivieren"
- "was mich am stärksten interessiert hat, war das Bauen"
- "wertebasierte Kultur"
- "strukturiert aufzubauen und wartbar zu halten"
- "Stakeholder" — stattdessen konkret: "Fachbereiche", "Forschende", "Kunden" etc.
- Kein Floskeln-Einstieg ("Hiermit bewerbe ich mich", "Mit großem Interesse")
- Stack-Disclaimer nicht als eigener Absatz — maximal ein eingebetteter Satz, nur wenn der
  fehlende Stack zentral und prominent in der Stelle ist
- Der `unternehmens_satz` darf kein isolierter Absatz sein — er muss in einen anderen
  Absatz integriert werden, als Teil eines Gedankens, nicht als Einschub

**Struktur:**
- 3–4 Absätze
- Jede Aussage hat einen konkreten Beleg oder Kontext
- Keine Citation-Tags, keine Quellenverweise im Text — nur plain text

---

Antworte ausschließlich mit einem JSON-Objekt, keine Erklärungen, kein Markdown:
{{
  "analyse": {{
    "unternehmens_differenziator": "... oder null",
    "gewaehlte_erfahrungen": ["pipeline", "geomar"],
    "weggelassen": "thesis — zu wenig Relevanz für diese Stelle weil ...",
    "stil_begruendung": "..."
  }},
  "unternehmens_satz": "... oder null",
  "kurzprofil": "2–3 Sätze, plain text, passend zur Stelle und Unternehmenskultur. Kein LaTeX. Tonalität wie das Kurzprofil im Kandidatenprofil. Variiert je nach Fokus: DE-Stelle → Pipeline/Cloud/Deployment; AI-Stelle → LLM-Engineering/Anthropic API/job-radar.",
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
        max_tokens=_THINKING_BUDGET + 6000,
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


def _pick_job_interactively(db_path: str) -> str:
    """Displays the top 10 unbeworben jobs and returns the refnr of the user's choice."""
    with get_connection(db_path) as conn:
        rows = conn.execute("""
            SELECT refnr, titel, arbeitgeber, fit_score, search_profile
            FROM jobs
            WHERE bewerbung_status IS NULL
            ORDER BY fit_score DESC NULLS LAST
            LIMIT 10
        """).fetchall()

    console = Console()

    if not rows:
        console.print("[red]Keine Jobs ohne Bewerbungsstatus gefunden.[/red]")
        sys.exit(1)

    table = Table(show_header=True, header_style="bold", box=None, pad_edge=False)
    table.add_column("nr",          justify="right", no_wrap=True)
    table.add_column("refnr",       style="dim",     no_wrap=True)
    table.add_column("titel",       max_width=40)
    table.add_column("arbeitgeber", max_width=30)
    table.add_column("score",       justify="right", no_wrap=True)
    table.add_column("profile",     no_wrap=True)

    for i, row in enumerate(rows, start=1):
        table.add_row(
            str(i),
            row["refnr"][-8:],
            row["titel"] or "",
            row["arbeitgeber"] or "",
            str(row["fit_score"]) if row["fit_score"] is not None else "",
            row["search_profile"] or "",
        )

    console.print("\n[bold]Jobs ohne Bewerbungsstatus (Top 10 nach Score):[/bold]\n")
    console.print(table)
    console.print()

    raw = input(f"Nummer eingeben (1–{len(rows)}): ").strip()
    try:
        choice = int(raw)
    except ValueError:
        console.print(f"[red]Ungültige Eingabe: '{raw}' ist keine Zahl.[/red]")
        sys.exit(1)

    if not 1 <= choice <= len(rows):
        console.print(f"[red]Ungültige Auswahl: {choice} liegt außerhalb von 1–{len(rows)}.[/red]")
        sys.exit(1)

    return rows[choice - 1]["refnr"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Anschreiben-Entwurf erstellen")
    parser.add_argument("--refnr", default=None,
                        help="Job-Referenznummer aus der DB (optional — interaktive Auswahl wenn weggelassen)")
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

    refnr = args.refnr or _pick_job_interactively(config.db_path)

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

    logger.info("Lade Job: %s", refnr)
    try:
        job = _fetch_job(config.db_path, refnr)
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

    update_bewerbung(
        config.db_path,
        refnr,
        entwurf=tex,
        status="entwurf",
        quellen=json.dumps(sources) if sources else None,
        analyse=json.dumps(values),
    )
    logger.info("bewerbung_status auf 'entwurf' gesetzt")


if __name__ == "__main__":
    main()