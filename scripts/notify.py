"""
notify.py — Send email notification for new high-score jobs after a pipeline run.

Usage (standalone):
    python scripts/notify.py --run-id <run_id>

Called from run_pipeline.py after each run automatically if NOTIFY_TO is set.
"""

import argparse
import logging
import os
import smtplib
import ssl
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)

MIN_SCORE = 4

# Score badge colors
_SCORE_COLORS = {5: "#2e7d32", 4: "#558b2f"}
_REMOTE_LABELS = {True: "✅ Remote", False: "🏢 Vor Ort", None: "—"}


@dataclass
class SmtpConfig:
    host: str
    port: int
    user: str
    password: str
    sender: str
    recipient: str


def smtp_config_from_env() -> SmtpConfig | None:
    """Build SmtpConfig from environment variables. Returns None if incomplete."""
    required = ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "NOTIFY_TO")
    missing = [k for k in required if not os.getenv(k)]
    if missing:
        logger.debug("Notification skipped — missing env vars: %s", ", ".join(missing))
        return None

    return SmtpConfig(
        host=os.getenv("SMTP_HOST"),
        port=int(os.getenv("SMTP_PORT", "587")),
        user=os.getenv("SMTP_USER"),
        password=os.getenv("SMTP_PASSWORD"),
        sender=os.getenv("SMTP_SENDER", os.getenv("SMTP_USER")),
        recipient=os.getenv("NOTIFY_TO"),
    )


def _fetch_new_high_score_jobs(
    db_path: str, run_id: int, search_profile: str = "flemming_koeln"
) -> list[dict]:
    """Return jobs first seen during run_id with fit_score >= MIN_SCORE.

    Approximates "inserted in this run" by comparing modifikationsTimestamp
    against the run's started_at. Not pixel-perfect but fine for notification
    purposes. Clean solution: add inserted_run_id column to jobs table.
    """
    query = """
        SELECT
            refnr, titel, arbeitgeber, ort,
            fit_score, remote, vertragsart, seniority,
            tech_stack, zusammenfassung, search_profile
        FROM jobs
        WHERE fit_score >= ?
          AND fetched_at >= (
              SELECT started_at FROM runs WHERE id = ?
          )
          AND notified_at IS NULL
          AND search_profile = ?
        ORDER BY fit_score DESC, titel
    """
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query, (MIN_SCORE, run_id, search_profile)).fetchall()
    return [dict(row) for row in rows]


def _score_badge(score: int | None) -> str:
    if score is None:
        return "<span>—</span>"
    color = _SCORE_COLORS.get(score, "#555")
    return (
        f'<span style="background:{color};color:#fff;'
        f'padding:2px 8px;border-radius:12px;font-weight:bold">'
        f'{score}/5</span>'
    )


def _job_row(job: dict) -> str:
    score_html = _score_badge(job.get("fit_score"))
    remote_label = _REMOTE_LABELS.get(job.get("remote"), "—")
    tech = job.get("tech_stack") or "—"
    summary = job.get("zusammenfassung") or ""
    employer = job.get("arbeitgeber") or "—"
    location = job.get("ort") or "—"

    return f"""
    <tr style="border-bottom:1px solid #eee">
      <td style="padding:12px 8px">
        <strong>{job['titel']}</strong><br>
        <span style="color:#555;font-size:0.9em">{employer} · {location}</span>
        {f'<br><span style="color:#666;font-size:0.85em">{summary}</span>' if summary else ''}
      </td>
      <td style="padding:12px 8px;white-space:nowrap">{score_html}</td>
      <td style="padding:12px 8px;white-space:nowrap">{remote_label}</td>
      <td style="padding:12px 8px;font-size:0.85em;color:#444">{tech}</td>
    </tr>"""


def _build_html(jobs: list[dict], run_id: int) -> str:
    rows_html = "".join(_job_row(j) for j in jobs)
    count = len(jobs)
    plural = "Job" if count == 1 else "Jobs"

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:sans-serif;max-width:800px;margin:0 auto;padding:24px;color:#222">
  <h2 style="margin-bottom:4px">🎯 {count} neuer {plural} mit Score ≥ {MIN_SCORE}</h2>
  <p style="color:#666;margin-top:0">Pipeline Run #{run_id}</p>
  <table style="width:100%;border-collapse:collapse">
    <thead>
      <tr style="background:#f5f5f5;text-align:left">
        <th style="padding:8px">Job</th>
        <th style="padding:8px">Score</th>
        <th style="padding:8px">Remote</th>
        <th style="padding:8px">Stack</th>
      </tr>
    </thead>
    <tbody>
      {rows_html}
    </tbody>
  </table>
  <p style="color:#aaa;font-size:0.8em;margin-top:24px">job-radar · automatisch generiert</p>
</body>
</html>"""


def _build_plaintext(jobs: list[dict], run_id: int) -> str:
    lines = [f"job-radar — {len(jobs)} neuer Job(s) mit Score >= {MIN_SCORE} (Run #{run_id})", ""]
    for j in jobs:
        lines.append(f"[{j.get('fit_score')}/5] {j['titel']}")
        lines.append(f"  {j.get('arbeitgeber', '—')} · {j.get('ort', '—')}")
        if j.get("zusammenfassung"):
            lines.append(f"  {j['zusammenfassung']}")
        lines.append("")
    return "\n".join(lines)


def send_notification(db_path: str, run_id: int, config: SmtpConfig) -> bool:
    """
    Query high-score jobs for run_id and send email.
    Returns True if mail was sent, False if no matching jobs.
    Raises on SMTP/connection errors.
    """
    jobs = _fetch_new_high_score_jobs(db_path, run_id, search_profile="flemming_koeln")

    if not jobs:
        logger.info("No jobs with score >= %d in run #%d — skipping notification", MIN_SCORE, run_id)
        return False

    logger.info("Sending notification for %d job(s) to %s", len(jobs), config.recipient)

    subject = f"job-radar: {len(jobs)} neuer Job{'s' if len(jobs) > 1 else ''} mit Score ≥ {MIN_SCORE}"
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = config.sender
    msg["To"] = config.recipient
    msg.attach(MIMEText(_build_plaintext(jobs, run_id), "plain", "utf-8"))
    msg.attach(MIMEText(_build_html(jobs, run_id), "html", "utf-8"))

    if config.port == 465:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(config.host, config.port, context=context) as smtp:
            smtp.login(config.user, config.password)
            smtp.sendmail(config.sender, config.recipient, msg.as_string())
    else:
        with smtplib.SMTP(config.host, config.port) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(config.user, config.password)
            smtp.sendmail(config.sender, config.recipient, msg.as_string())

    now = datetime.now(timezone.utc).isoformat()
    refnrs = [j["refnr"] for j in jobs]
    placeholders = ",".join("?" * len(refnrs))
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            f"UPDATE jobs SET notified_at = ? WHERE refnr IN ({placeholders})",
            [now, *refnrs],
        )

    logger.info("Notification sent: %s", subject)
    return True


def notify_if_configured(db_path: str, run_id: int) -> None:
    """
    Convenience wrapper for run_pipeline.py.
    Reads config from env, skips silently if not configured, logs errors without raising.
    """
    config = smtp_config_from_env()
    if config is None:
        return
    try:
        send_notification(db_path, run_id, config)
    except smtplib.SMTPAuthenticationError as e:
        logger.error("SMTP auth failed — check SMTP_USER / SMTP_PASSWORD: %s", e)
    except smtplib.SMTPException as e:
        logger.error("SMTP error sending notification: %s", e)
    except sqlite3.Error as e:
        logger.error("DB error fetching jobs for notification: %s", e)


if __name__ == "__main__":
    import sys
    from dotenv import load_dotenv

    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Send job-radar notification for a pipeline run")
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--db", default=os.getenv("DB_PATH", "job_radar.db"))
    args = parser.parse_args()

    cfg = smtp_config_from_env()
    if cfg is None:
        logger.error("SMTP not configured — set SMTP_HOST, SMTP_USER, SMTP_PASSWORD, NOTIFY_TO in .env")
        sys.exit(1)

    sent = send_notification(args.db, args.run_id, cfg)
    sys.exit(0 if sent else 0)
