import argparse
from rich.console import Console
from rich.table import Table
from job_radar.config import Config
from job_radar.db.models import get_connection


def _trunc(value: str | None, max_len: int) -> str:
    if not value:
        return ""
    return value if len(value) <= max_len else value[: max_len - 1] + "…"


def _date_only(value: str | None) -> str:
    if not value:
        return ""
    return value[:10]


def _score_style(score: int | None) -> str:
    if score is None:
        return "dim"
    if score >= 4:
        return "bold green"
    if score >= 3:
        return "yellow"
    return "red"


def show(
    db_path: str,
    min_score: int | None = None,
    profile: str | None = None,
    bewerbung_status: str | None = None,
) -> None:
    conditions: list[str] = []
    params: list = []

    if min_score is not None:
        conditions.append("fit_score >= ?")
        params.append(min_score)
    if profile is not None:
        conditions.append("search_profile = ?")
        params.append(profile)
    if bewerbung_status is not None:
        conditions.append("bewerbung_status = ?")
        params.append(bewerbung_status)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    with get_connection(db_path) as conn:
        rows = conn.execute(
            f"""
            SELECT refnr, titel, arbeitgeber, ort, remote, seniority, fit_score, fetched_at
            FROM jobs
            {where}
            ORDER BY fit_score DESC NULLS LAST
            """,
            params,
        ).fetchall()

    filter_parts: list[str] = []
    if min_score is not None:
        filter_parts.append(f"score ≥ {min_score}")
    if profile is not None:
        filter_parts.append(f"profile: {profile}")
    if bewerbung_status is not None:
        filter_parts.append(f"bewerbung_status: {bewerbung_status}")

    table = Table(show_header=True, header_style="bold", box=None, pad_edge=False)
    table.add_column("refnr",       style="dim",  no_wrap=True)
    table.add_column("titel",       max_width=40)
    table.add_column("arbeitgeber", max_width=30)
    table.add_column("ort",         no_wrap=True)
    table.add_column("remote",      no_wrap=True)
    table.add_column("seniority",   no_wrap=True)
    table.add_column("score",       justify="right", no_wrap=True)
    table.add_column("fetched",     no_wrap=True)

    for row in rows:
        score = row["fit_score"]
        table.add_row(
            row["refnr"][-8:],
            _trunc(row["titel"], 40),
            _trunc(row["arbeitgeber"], 30),
            row["ort"] or "",
            row["remote"] or "",
            row["seniority"] or "",
            str(score) if score is not None else "",
            _date_only(row["fetched_at"]),
            style=_score_style(score),
        )

    console = Console()
    console.print(f"\n[bold]{len(rows)} job(s) found[/bold]\n")
    if filter_parts:
        console.print(f"[dim]Filter: {' | '.join(filter_parts)}[/dim]\n")
    console.print(table)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Zeigt Jobs aus der Datenbank als formatierte Tabelle.")
    parser.add_argument("--min-score", type=int, default=None, metavar="INT",
                        help="Nur Jobs mit fit_score >= INT anzeigen")
    parser.add_argument("--profile", type=str, default=None, metavar="TEXT",
                        help="Nur Jobs mit diesem search_profile anzeigen (z.B. koeln)")
    parser.add_argument("--bewerbung-status", type=str, default=None, metavar="TEXT",
                        help="Nur Jobs mit diesem bewerbung_status anzeigen (z.B. entwurf)")
    args = parser.parse_args()

    show(
        Config().db_path,
        min_score=args.min_score,
        profile=args.profile,
        bewerbung_status=args.bewerbung_status,
    )
