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


def show(db_path: str) -> None:
    with get_connection(db_path) as conn:
        rows = conn.execute("""
            SELECT refnr, titel, arbeitgeber, ort, remote, seniority, fit_score, fetched_at
            FROM jobs
            ORDER BY fit_score DESC NULLS LAST
        """).fetchall()

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
    console.print(table)


if __name__ == "__main__":
    show(Config().db_path)
