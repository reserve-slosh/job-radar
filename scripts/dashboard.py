"""Streamlit dashboard for job-radar.

Launch:
    streamlit run scripts/dashboard.py

Tabs:
    Jobs     — filterable job table, click a row to open detail view
    Detail   — full job info, cover letter generation and download
    Runs     — pipeline run history, manual pipeline trigger
"""

import json
import logging
import subprocess
import sys
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

# Ensure project root is on sys.path when running via `streamlit run`
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from job_radar.config import Config, load_profiles
from job_radar.db.models import get_connection, get_job_url, update_bewerbung, init_db

load_dotenv()
logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SCORE_COLORS = {5: "🟢", 4: "🟢", 3: "🟡", 2: "🔴", 1: "🔴"}
_STATUS_LABELS = {
    None: "—",
    "entwurf": "📝 Entwurf",
    "abgeschickt": "✅ Abgeschickt",
}


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def _load_jobs(db_path: str, filters: dict) -> list[dict]:
    query = """
        SELECT refnr, titel, arbeitgeber, ort, fit_score, seniority, remote,
               vertragsart, bewerbung_status, search_profile, source,
               zusammenfassung, tech_stack, eintrittsdatum, veroeffentlicht_am,
               bewerbung_entwurf, bewerbung_quellen, bewerbung_analyse, duplicate_of, fetched_at,
               titel_normalisiert, raw_text
        FROM jobs
        WHERE 1=1
    """
    params: list = []

    if filters.get("search_profile"):
        placeholders = ",".join("?" * len(filters["search_profile"]))
        query += f" AND search_profile IN ({placeholders})"
        params.extend(filters["search_profile"])

    if filters.get("score_min") is not None:
        query += " AND fit_score >= ?"
        params.append(filters["score_min"])

    if filters.get("score_max") is not None:
        query += " AND fit_score <= ?"
        params.append(filters["score_max"])

    if filters.get("seniority"):
        placeholders = ",".join("?" * len(filters["seniority"]))
        query += f" AND seniority IN ({placeholders})"
        params.extend(filters["seniority"])

    if filters.get("remote"):
        placeholders = ",".join("?" * len(filters["remote"]))
        query += f" AND remote IN ({placeholders})"
        params.extend(filters["remote"])

    if filters.get("bewerbung_status") is not None:
        if "null" in filters["bewerbung_status"]:
            non_null = [s for s in filters["bewerbung_status"] if s != "null"]
            if non_null:
                placeholders = ",".join("?" * len(non_null))
                query += f" AND (bewerbung_status IS NULL OR bewerbung_status IN ({placeholders}))"
                params.extend(non_null)
            else:
                query += " AND bewerbung_status IS NULL"
        else:
            placeholders = ",".join("?" * len(filters["bewerbung_status"]))
            query += f" AND bewerbung_status IN ({placeholders})"
            params.extend(filters["bewerbung_status"])

    if filters.get("duplicate_of") == "hide":
        query += " AND duplicate_of IS NULL"

    query += " ORDER BY fit_score DESC NULLS LAST, fetched_at DESC"

    with get_connection(db_path) as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def _load_runs(db_path: str) -> list[dict]:
    with get_connection(db_path) as conn:
        rows = conn.execute("""
            SELECT id, started_at, finished_at, search_profile,
                   jobs_fetched, jobs_new, jobs_updated, jobs_skipped,
                   jobs_failed, status, error_msg
            FROM runs
            ORDER BY started_at DESC
            LIMIT 100
        """).fetchall()
    return [dict(r) for r in rows]


def _get_all_search_profiles(db_path: str) -> list[str]:
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT DISTINCT search_profile FROM jobs WHERE search_profile IS NOT NULL ORDER BY 1"
        ).fetchall()
    return [r[0] for r in rows]


# ---------------------------------------------------------------------------
# Tab: Jobs
# ---------------------------------------------------------------------------

def _render_jobs_tab(config: Config) -> None:
    all_profiles = _get_all_search_profiles(config.db_path)

    with st.sidebar:
        st.header("Filter")

        selected_profiles = st.multiselect(
            "Search Profile",
            options=all_profiles,
            default=all_profiles,
        )

        score_range = st.slider("Fit Score", min_value=1, max_value=5, value=(1, 5))

        seniority_opts = ["junior", "mid", "senior", "lead", "unknown"]
        selected_seniority = st.multiselect("Seniority", seniority_opts, default=seniority_opts)

        remote_opts = ["remote", "hybrid", "onsite", "unknown"]
        selected_remote = st.multiselect("Remote", remote_opts, default=remote_opts)

        status_opts = {"Offen": "null", "Entwurf": "entwurf", "Abgeschickt": "abgeschickt"}
        selected_status_labels = st.multiselect(
            "Bewerbungsstatus", list(status_opts.keys()), default=list(status_opts.keys())
        )
        selected_status = [status_opts[l] for l in selected_status_labels]

        hide_duplicates = st.checkbox("Duplikate ausblenden", value=True)

    filters = {
        "search_profile": selected_profiles,
        "score_min": score_range[0],
        "score_max": score_range[1],
        "seniority": selected_seniority,
        "remote": selected_remote,
        "bewerbung_status": selected_status,
        "duplicate_of": "hide" if hide_duplicates else None,
    }

    jobs = _load_jobs(config.db_path, filters)
    st.caption(f"{len(jobs)} Jobs")

    if not jobs:
        st.info("Keine Jobs mit diesen Filtern.")
        return

    header = st.columns([3, 2, 1, 1, 1, 1, 1])
    for col, label in zip(header, ["Titel", "Arbeitgeber", "Score", "Seniority", "Remote", "Status", "Profil"]):
        col.markdown(f"**{label}**")
    st.divider()

    for job in jobs:
        score = job["fit_score"]
        score_icon = _SCORE_COLORS.get(score, "⚪")
        status_label = _STATUS_LABELS.get(job["bewerbung_status"], job["bewerbung_status"] or "—")
        dup_badge = " 🔁" if job.get("duplicate_of") else ""

        cols = st.columns([3, 2, 1, 1, 1, 1, 1])
        cols[0].write(f"{job['titel'] or '—'}{dup_badge}")
        cols[1].write(job["arbeitgeber"] or "—")
        cols[2].write(f"{score_icon} {score}" if score else "—")
        cols[3].write(job["seniority"] or "—")
        cols[4].write(job["remote"] or "—")
        cols[5].write(status_label)
        cols[6].write(job["search_profile"] or "—")

        if cols[0].button("Detail →", key=f"btn_{job['refnr']}", use_container_width=False):
            st.session_state["selected_refnr"] = job["refnr"]
            st.session_state["active_tab"] = 1
            st.rerun()

        st.divider()


# ---------------------------------------------------------------------------
# Tab: Detail & Bewerbung
# ---------------------------------------------------------------------------

def _render_detail_tab(config: Config) -> None:
    refnr = st.session_state.get("selected_refnr")

    if not refnr:
        st.info("Kein Job ausgewählt. Wähle einen Job im Tab **Jobs**.")
        return

    jobs = _load_jobs(config.db_path, {})
    job = next((j for j in jobs if j["refnr"] == refnr), None)

    if not job:
        st.warning(f"Job `{refnr}` nicht in der DB gefunden.")
        return

    # Header
    st.subheader(job["titel"] or "—")
    url = get_job_url(job["refnr"], job["source"])
    col1, col2, col3 = st.columns(3)
    col1.metric("Fit Score", f"{job['fit_score']}/5" if job["fit_score"] else "—")
    col2.metric("Seniority", job["seniority"] or "—")
    col3.metric("Remote", job["remote"] or "—")

    st.markdown(f"**{job['arbeitgeber']}** · {job['ort'] or '—'} · {job['search_profile'] or '—'}")
    if url:
        st.markdown(f"[🔗 Zum Inserat]({url})")

    if job.get("duplicate_of"):
        st.warning(f"🔁 Mögliches Duplikat von `{job['duplicate_of']}`")

    # Job JSON download — always available
    arbeitgeber_slug = (job["arbeitgeber"] or "unbekannt").lower().replace(" ", "_")[:30]
    llm_extra = {}
    if job.get("bewerbung_analyse"):
        try:
            llm = json.loads(job["bewerbung_analyse"])
            llm_extra = {
                "analyse": llm.get("analyse"),
                "unternehmens_satz": llm.get("unternehmens_satz"),
                "kurzprofil": llm.get("kurzprofil"),
            }
        except (json.JSONDecodeError, TypeError):
            pass
    job_json = json.dumps({
        k: job[k] for k in (
            "refnr", "titel", "arbeitgeber", "ort", "fit_score",
            "seniority", "remote", "vertragsart", "zusammenfassung",
            "tech_stack", "eintrittsdatum", "veroeffentlicht_am",
            "search_profile", "source",
        )
    } | llm_extra, ensure_ascii=False, indent=2)
    st.download_button(
        label="⬇️ Job als .json",
        data=job_json,
        file_name=f"job_{arbeitgeber_slug}.json",
        mime="application/json",
    )

    st.divider()

    # Zusammenfassung & Tech Stack
    col_left, col_right = st.columns(2)
    with col_left:
        st.markdown("**Zusammenfassung**")
        st.write(job["zusammenfassung"] or "—")
    with col_right:
        st.markdown("**Tech Stack**")
        if job["tech_stack"]:
            try:
                stack = json.loads(job["tech_stack"])
                st.write(", ".join(stack))
            except (json.JSONDecodeError, TypeError):
                st.write(job["tech_stack"])
        else:
            st.write("—")

    with st.expander("Vollständige Stellenbeschreibung"):
        st.text(job.get("raw_text") or "Kein Text verfügbar.")

    st.divider()

    # LLM Analyse & Recherche
    if job.get("bewerbung_analyse"):
        try:
            llm = json.loads(job["bewerbung_analyse"])
            analyse = llm.get("analyse")
            unternehmens_satz = llm.get("unternehmens_satz")
            if analyse or unternehmens_satz:
                with st.expander("🔍 LLM-Analyse"):
                    if unternehmens_satz:
                        st.markdown("**Unternehmensbezug im Brief**")
                        st.info(unternehmens_satz)
                    kurzprofil = llm.get("kurzprofil")
                    if kurzprofil:
                        st.markdown("**Kurzprofil-Vorschlag**")
                        st.info(kurzprofil)
                    if analyse:
                        if analyse.get("unternehmens_differenziator"):
                            st.markdown("**Differenziator**")
                            st.write(analyse["unternehmens_differenziator"])
                        if analyse.get("gewaehlte_erfahrungen"):
                            st.markdown("**Gewählte Erfahrungen**")
                            st.write(", ".join(analyse["gewaehlte_erfahrungen"]))
                        if analyse.get("weggelassen"):
                            st.markdown("**Weggelassen**")
                            st.write(analyse["weggelassen"])
                        if analyse.get("stil_begruendung"):
                            st.markdown("**Stil-Entscheidung**")
                            st.write(analyse["stil_begruendung"])
        except (json.JSONDecodeError, TypeError):
            pass

    if job.get("bewerbung_quellen"):
        try:
            quellen = json.loads(job["bewerbung_quellen"])
            if quellen:
                with st.expander("🌐 Recherche-Quellen (Web Search)"):
                    for url_q in quellen:
                        st.markdown(f"- {url_q}")
        except (json.JSONDecodeError, TypeError):
            pass

    # Bewerbungsassistent
    st.markdown("### Bewerbung")
    status = job.get("bewerbung_status")

    if status == "abgeschickt":
        st.success("✅ Bewerbung bereits abgeschickt.")
    else:
        candidates = load_profiles(config.profiles_dir)
        candidate_names = [c.name for c in candidates]
        profile_key = job.get("search_profile", "")
        default_candidate = profile_key.split("_")[0] if profile_key else candidate_names[0]
        default_idx = candidate_names.index(default_candidate) if default_candidate in candidate_names else 0

        selected_candidate_name = st.selectbox(
            "Kandidat", candidate_names, index=default_idx, key="detail_candidate"
        )

        col_gen, col_mark = st.columns(2)

        with col_gen:
            if st.button("📝 Entwurf erstellen", disabled=not config.anthropic_api_key):
                _generate_cover_letter(config, job, selected_candidate_name)

        with col_mark:
            if st.button("✅ Als abgeschickt markieren"):
                update_bewerbung(config.db_path, refnr, status="abgeschickt")
                st.success("Status aktualisiert.")
                st.rerun()

    # Entwurf anzeigen + Download
    if job.get("bewerbung_entwurf"):
        st.divider()
        st.markdown("**Vorhandener Entwurf**")
        arbeitgeber_slug = (job["arbeitgeber"] or "unbekannt").lower().replace(" ", "_")[:30]
        st.download_button(
            label="⬇️ .tex herunterladen",
            data=job["bewerbung_entwurf"],
            file_name=f"anschreiben_{arbeitgeber_slug}.tex",
            mime="text/plain",
        )


def _generate_cover_letter(config: Config, job: dict, candidate_name: str) -> None:
    """Calls the Bewerbungsassistent logic inline and updates the DB."""
    candidates = load_profiles(config.profiles_dir)
    candidate = next((c for c in candidates if c.name == candidate_name), None)

    if not candidate:
        st.error(f"Kandidat '{candidate_name}' nicht gefunden.")
        return
    if not candidate.profile_text:
        st.error(f"Profil für '{candidate_name}' ist leer.")
        return

    template_path = _PROJECT_ROOT / "templates" / "anschreiben_template.tex"
    if not template_path.exists():
        st.error(f"Template nicht gefunden: {template_path}")
        return

    template = template_path.read_text(encoding="utf-8")

    # Import bewerbung helpers inline to avoid circular imports
    import importlib.util
    bewerbung_path = _PROJECT_ROOT / "scripts" / "bewerbung.py"
    spec = importlib.util.spec_from_file_location("bewerbung", bewerbung_path)
    bewerbung = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bewerbung)

    with st.spinner("Sonnet analysiert die Stelle und recherchiert das Unternehmen..."):
        try:
            prompt = bewerbung._build_prompt(candidate.profile_text, job)
            values, sources = bewerbung._call_sonnet(prompt, config.anthropic_api_key)
            tex = bewerbung._fill_template(template, values)

            update_bewerbung(
                config.db_path,
                job["refnr"],
                entwurf=tex,
                status="entwurf",
                quellen=json.dumps(sources) if sources else None,
                analyse=json.dumps(values),
            )
            st.success(f"Entwurf erstellt (Stil {values.get('stil', '?')}). Seite neu laden für Download.")
            st.rerun()
        except Exception as e:
            st.error(f"Fehler: {e}")
            logger.exception("Fehler beim Erstellen des Entwurfs")


# ---------------------------------------------------------------------------
# Tab: Runs
# ---------------------------------------------------------------------------

def _render_runs_tab(config: Config) -> None:
    st.markdown("### Pipeline ausführen")

    candidates = load_profiles(config.profiles_dir)
    candidate_names = [c.name for c in candidates]

    col_sel, col_btn = st.columns([2, 1])
    with col_sel:
        selected_candidates = st.multiselect(
            "Kandidaten",
            candidate_names,
            default=candidate_names,
            key="run_candidates",
        )
    with col_btn:
        st.markdown("<br>", unsafe_allow_html=True)
        run_disabled = (
            not selected_candidates
            or st.session_state.get("pipeline_running", False)
        )
        if st.button("▶️ Pipeline starten", disabled=run_disabled):
            st.session_state["pipeline_running"] = True
            _trigger_pipeline(config, selected_candidates)
            st.session_state["pipeline_running"] = False

    st.divider()

    st.markdown("### Run-Historie")
    runs = _load_runs(config.db_path)

    if not runs:
        st.info("Noch keine Pipeline-Runs.")
        return

    for run in runs:
        status_icon = "✅" if run["status"] == "success" else ("❌" if run["status"] == "error" else "⏳")
        started = (run["started_at"] or "")[:16].replace("T", " ")
        finished = (run["finished_at"] or "")[:16].replace("T", " ")
        cols = st.columns([1, 2, 1, 1, 1, 1, 1, 1])
        cols[0].write(status_icon)
        cols[1].write(run["search_profile"] or run.get("source") or "—")
        cols[2].write(started)
        cols[3].write(finished or "—")
        cols[4].write(f"📥 {run['jobs_fetched']}")
        cols[5].write(f"🆕 {run['jobs_new']}")
        cols[6].write(f"🔄 {run['jobs_updated']}")
        cols[7].write(f"⏭️ {run['jobs_skipped']}")
        if run.get("error_msg"):
            with st.expander(f"Fehler: {run['error_msg'][:60]}"):
                st.code(run["error_msg"])
        st.divider()


def _trigger_pipeline(config: Config, candidate_names: list[str]) -> None:
    """Runs run_pipeline.py as a subprocess and streams output to Streamlit."""
    pipeline_script = _PROJECT_ROOT / "scripts" / "run_pipeline.py"
    python_exe = sys.executable

    # Pass selected candidates via env so run_pipeline can filter
    import os
    env = os.environ.copy()
    env["PIPELINE_CANDIDATES"] = ",".join(candidate_names)

    output_area = st.empty()
    log_lines: list[str] = []

    try:
        process = subprocess.Popen(
            [python_exe, str(pipeline_script)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
            cwd=str(_PROJECT_ROOT),
        )

        for line in process.stdout:
            log_lines.append(line.rstrip())
            output_area.code("\n".join(log_lines[-30:]))

        process.wait()
        if process.returncode == 0:
            st.success("Pipeline erfolgreich abgeschlossen.")
        else:
            st.error(f"Pipeline mit Code {process.returncode} beendet.")

    except Exception as e:
        st.error(f"Fehler beim Starten der Pipeline: {e}")
        logger.exception("Pipeline-Trigger fehlgeschlagen")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    st.set_page_config(
        page_title="job-radar",
        page_icon="📡",
        layout="wide",
    )
    st.title("📡 job-radar")

    config = Config()
    init_db(config.db_path)

    tab_labels = ["🗂️ Jobs", "📋 Detail & Bewerbung", "⚙️ Runs"]
    active = st.session_state.get("active_tab", 0)

    tabs = st.tabs(tab_labels)

    with tabs[0]:
        _render_jobs_tab(config)

    with tabs[1]:
        _render_detail_tab(config)

    with tabs[2]:
        _render_runs_tab(config)


if __name__ == "__main__":
    main()