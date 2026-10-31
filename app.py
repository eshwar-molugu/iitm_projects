"""Streamlit UI. All evaluation work is delegated to agents.orchestrator.run_evaluation."""
from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

from agents import evaluation_agent
from agents.evaluation_agent import PROVIDERS, EvaluationError
from agents.orchestrator import TIE_BREAK_ORDER, InputError, WorkflowError, run_evaluation, validate_supplier_inputs
from db import init_db as dbmod
from db.init_db import load_active_criteria

ROOT = Path(__file__).resolve().parent
SAMPLE_DIR = ROOT / "data" / "rfps"
SAMPLES = [
    {"supplier_name": "Apex Systems", "file": "Apex_Systems.pdf", "date": "2026-03-02", "rating": 8},
    {"supplier_name": "BrightPath Tech", "file": "BrightPath_Tech.pdf", "date": "2026-03-04", "rating": 3},
    {"supplier_name": "NexaWorks", "file": "NexaWorks.pdf", "date": "2026-03-03", "rating": 7},
    {"supplier_name": "Orbit Digital", "file": "Orbit_Digital.pdf", "date": "2026-03-01", "rating": 9},
]

st.set_page_config(page_title="Agentic RFP Evaluation", layout="wide")
st.title("Agentic RFP Evaluation and Supplier Ranking")


def resolve_key(provider: str, typed: str):
    """Typed key, then Streamlit secrets, then environment variable."""
    if typed and typed.strip():
        return typed.strip()
    env_var = PROVIDERS[provider]["env_var"]
    try:
        secret = st.secrets[env_var]
        if secret:
            return str(secret).strip()
    except Exception:
        pass
    return os.environ.get(env_var, "").strip() or None


# ---- Setup: database and criteria -------------------------------------------------
dbmod.init_db(dbmod.DB_PATH)
_conn = dbmod.get_connection(dbmod.DB_PATH)
try:
    criteria = load_active_criteria(_conn)
finally:
    _conn.close()

# ---- Sidebar ------------------------------------------------------------------------
with st.sidebar:
    st.header("Settings")
    provider = st.selectbox(
        "LLM provider",
        options=list(PROVIDERS),
        format_func=lambda key: PROVIDERS[key]["label"],
        key="provider",
    )
    info = PROVIDERS[provider]
    typed_key = st.text_input(f"{info['label']} API key", type="password", key=f"key_{provider}")
    model = st.text_input(f"{info['label']} model", value=info["default_model"], key=f"model_{provider}")
    st.caption("The LLM only judges proposal content. Python does all arithmetic, benchmarks, tie-breaks and ranks.")

tab_criteria, tab_input, tab_board, tab_card, tab_run = st.tabs(
    ["Criteria", "Supplier input", "Leaderboard", "Detailed scorecard", "Run details"]
)

# ---- Criteria -----------------------------------------------------------------------
with tab_criteria:
    st.subheader("Active evaluation criteria")
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "ID": c["criterion_id"],
                    "Criterion": c["name"],
                    "Description": c["description"],
                    "Weight (%)": c["weight"],
                    "Max score": c["max_score"],
                }
                for c in criteria
            ]
        ),
        hide_index=True,
    )
    total_weight = sum(c["weight"] for c in criteria)
    if abs(total_weight - 100) < 1e-9:
        st.success("Active weights total 100%.")
    else:
        st.warning(f"Active weights total {total_weight:g}%, not 100%. Scores will be rescaled to 0-100.")

# ---- Supplier input -----------------------------------------------------------------
with tab_input:
    st.subheader("Supplier input")
    uploads = st.file_uploader("Supplier RFP PDFs", type=["pdf"], accept_multiple_files=True, key="uploads")

    col_load, col_clear = st.columns(2)
    if col_load.button("Load sample RFPs"):
        st.session_state["samples_loaded"] = True
    if col_clear.button("Clear samples"):
        st.session_state["samples_loaded"] = False

    rows = []
    if st.session_state.get("samples_loaded"):
        for sample in SAMPLES:
            path = SAMPLE_DIR / sample["file"]
            if path.exists():
                rows.append(
                    {
                        "id": f"sample-{sample['file']}",
                        "filename": sample["file"],
                        "bytes": path.read_bytes(),
                        "name": sample["supplier_name"],
                        "date": date.fromisoformat(sample["date"]),
                        "rating": float(sample["rating"]),
                    }
                )
    for upload in uploads or []:
        rows.append(
            {
                "id": f"upload-{upload.name}-{upload.size}",
                "filename": upload.name,
                "bytes": upload.getvalue(),
                "name": Path(upload.name).stem.replace("_", " "),
                "date": date.today(),
                "rating": 0.0,
            }
        )

    supplier_inputs = []
    if rows:
        st.markdown("**Supplier details**")
        for row in rows:
            st.caption(row["filename"])
            c_name, c_date, c_rating = st.columns(3)
            name = c_name.text_input("Supplier name", value=row["name"], key=f"name_{row['id']}")
            submitted_on = c_date.date_input("Submission date", value=row["date"], key=f"date_{row['id']}")
            rating = c_rating.number_input(
                "Historical experience rating (0-10)",
                min_value=0.0,
                max_value=10.0,
                value=row["rating"],
                step=0.5,
                key=f"rating_{row['id']}",
            )
            supplier_inputs.append(
                {
                    "supplier_name": name,
                    "submission_date": submitted_on,
                    "experience_rating": rating,
                    "filename": row["filename"],
                    "pdf_bytes": row["bytes"],
                }
            )
    else:
        st.info("Upload supplier PDFs or click **Load sample RFPs** to begin.")

    if st.button("Evaluate suppliers", type="primary"):
        errors = validate_supplier_inputs(supplier_inputs)[1] if supplier_inputs else ["Upload at least two supplier proposals so they can be compared with peers."]
        if errors:
            for message in errors:
                st.error(message)
        else:
            api_key = resolve_key(provider, typed_key)
            if not api_key:
                st.error(f"Enter your {info['label']} API key in the sidebar (or configure {info['env_var']}).")
            else:
                try:
                    client = evaluation_agent.get_client(api_key, provider)
                    conn = dbmod.get_connection(dbmod.DB_PATH)
                    try:
                        with st.status("Running evaluation...", expanded=True) as status:
                            result = run_evaluation(conn, client, supplier_inputs, model=model, progress=st.write)
                            status.update(label="Evaluation complete", state="complete")
                        st.session_state["result"] = result
                    finally:
                        conn.close()
                    st.success("Done. Open the **Leaderboard**, **Detailed scorecard** and **Run details** tabs.")
                    if result["warnings"]:
                        st.warning(f"The run finished with {len(result['warnings'])} warning(s). See **Run details**.")
                except (EvaluationError, WorkflowError, InputError) as exc:
                    st.error(str(exc))

result = st.session_state.get("result")

# ---- Leaderboard --------------------------------------------------------------------
with tab_board:
    if not result:
        st.info("Run an evaluation in the **Supplier input** tab to see the leaderboard.")
    else:
        st.subheader(f"Leaderboard - {result['rfp_run_id']}")
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Rank": s["final_rank"],
                        "Supplier": s["supplier_name"],
                        "Absolute score": s["absolute_score"],
                        "PPI": s["ppi"],
                        "Submission date": s["submission_date"],
                        "Experience rating": s["experience_rating"],
                    }
                    for s in result["suppliers"]
                ]
            ),
            hide_index=True,
            column_config={
                "Absolute score": st.column_config.NumberColumn(format="%.2f"),
                "PPI": st.column_config.NumberColumn(format="%.2f"),
                "Experience rating": st.column_config.NumberColumn(format="%.2f"),
            },
        )
        st.caption(
            "Ranked by PPI (higher is better), then earlier submission date, then higher experience rating, "
            "then supplier name. Absolute score is the weighted total out of 100."
        )
        for skipped in result["skipped_suppliers"]:
            st.warning(f"{skipped['supplier_name']} excluded from ranking: {skipped['reason']}")

# ---- Detailed scorecard -------------------------------------------------------------
with tab_card:
    if not result:
        st.info("Run an evaluation first to see scorecards.")
    else:
        names = [s["supplier_name"] for s in result["suppliers"]]
        chosen = st.selectbox("Supplier", names, key="scorecard_supplier")
        supplier = next(s for s in result["suppliers"] if s["supplier_name"] == chosen)

        m1, m2, m3 = st.columns(3)
        m1.metric("Rank", supplier["final_rank"])
        m2.metric("Absolute score", f"{supplier['absolute_score']:.2f}")
        m3.metric("PPI", f"{supplier['ppi']:.2f}")

        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Criterion": r["criterion_name"],
                        "Score": r["score"],
                        "Max": r["max_score"],
                        "Benchmark": r["benchmark"],
                        "Gap": r["gap"],
                        "Relative %": r["relative_pct"],
                        "Weight (%)": r["weight"],
                        "Weighted score": r["weighted_score"],
                    }
                    for r in supplier["criteria"]
                ]
            ),
            hide_index=True,
            column_config={
                "Relative %": st.column_config.NumberColumn(format="%.2f"),
                "Weighted score": st.column_config.NumberColumn(format="%.2f"),
                "Gap": st.column_config.NumberColumn(format="%.2f"),
                "Weight (%)": st.column_config.NumberColumn(format="%.2f"),
            },
        )

        st.subheader("Justification and evidence")
        for r in supplier["criteria"]:
            label = f"{r['criterion_name']}: {r['score']:g}/{r['max_score']:g}"
            if not r["is_valid"]:
                label += " (repaired)"
            with st.expander(label):
                st.markdown(f"**Justification:** {r['justification']}")
                st.markdown(f"**Evidence:** {r['evidence']}")

        st.markdown(f"**Summary:** {supplier['overall_summary']}")
        if supplier["risks"]:
            st.markdown("**Risks:**")
            for risk in supplier["risks"]:
                st.markdown(f"- {risk}")
        if supplier["warnings"]:
            st.markdown("**Warnings for this supplier:**")
            for warning in supplier["warnings"]:
                st.markdown(f"- {warning}")

# ---- Run details --------------------------------------------------------------------
with tab_run:
    if not result:
        st.info("Run details appear after an evaluation.")
    else:
        m1, m2, m3 = st.columns(3)
        m1.metric("RFP_RUN_ID", result["rfp_run_id"])
        m2.metric("Status", result["status"])
        m3.metric("Model", result["model"])

        st.subheader("Tie-break order")
        for index, rule in enumerate(TIE_BREAK_ORDER, start=1):
            st.markdown(f"{index}. {rule}")

        st.subheader("How adjacent ranks were decided")
        if result["tie_break_notes"]:
            for note in result["tie_break_notes"]:
                st.markdown(f"- {note}")
        else:
            st.write("Only one supplier was ranked, so there are no adjacent pairs to compare.")

        if result["warnings"]:
            st.subheader(f"Warnings ({len(result['warnings'])})")
            for warning in result["warnings"]:
                st.markdown(f"- {warning}")
        else:
            st.success("No warnings.")

        with st.expander("Criteria used for this run"):
            st.dataframe(pd.DataFrame(result["criteria"]), hide_index=True)

        st.download_button(
            "Download complete result (JSON)",
            data=json.dumps(result, indent=2, ensure_ascii=False),
            file_name=f"{result['rfp_run_id']}.json",
            mime="application/json",
        )
