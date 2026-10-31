# Agentic RFP Evaluation and Supplier Ranking

An AI-assisted procurement tool. It reads supplier RFP responses (PDF), has an LLM score each one against
configurable criteria with cited evidence, then **deterministic Python** benchmarks suppliers against their peers
and produces an explainable leaderboard. Built with Streamlit, SQLite and your choice of LLM (OpenAI, Anthropic Claude or Google Gemini).

**Live app:** _add your Streamlit Community Cloud URL here after deploying_

> The LLM judges proposal content only. It never computes totals, benchmarks, tie-breaks or ranks.

## Screenshots

| Criteria | Supplier input |
|---|---|
| ![Criteria](docs/screenshots/01_criteria.png) | ![Supplier input](docs/screenshots/02_supplier_input.png) |

Validation error (blank supplier name is rejected before anything is stored or sent to the LLM):

![Validation error](docs/screenshots/07_validation_error.png)

Result screens (produced by `scripts/capture_screenshots.py` after a real run, see "Screenshots" below):

![Leaderboard](docs/screenshots/04_leaderboard.png)
![Scorecard](docs/screenshots/05_scorecard.png)
![Run details](docs/screenshots/06_run_details.png)

## Architecture

```
Streamlit UI (app.py)  /  Jupyter lab (rfp_lab.ipynb)
            |
            v
Orchestrator  agents/orchestrator.py  run_evaluation()
   1 load active criteria (SQLite)      6 score  \
   2 validate supplier inputs           7 benchmark  > tools/ranking.py (deterministic)
   3 create batch + RFP_RUN_ID          8 rank      /
   4 per supplier:                      9 persist (one transaction)
       tools/document.py   PDF -> text  10 return full run export (JSON)
       agents/evaluation_agent.py  LLM -> raw JSON
       tools/validation.py raw JSON -> validated scores + warnings
```

| Component | File | Responsibility |
|---|---|---|
| Orchestrator Agent | `agents/orchestrator.py` | Runs the workflow in order, isolates per-supplier failures |
| Document Tool | `tools/document.py` | PyMuPDF text extraction; rejects corrupt, encrypted or scanned PDFs |
| Evaluation Agent | `agents/evaluation_agent.py` | Builds the prompt from active criteria, calls the selected provider: OpenAI, Anthropic or Gemini (JSON output, temperature 0, 1 retry) |
| Validation Tool | `tools/validation.py` | Parses JSON, fills missing criteria, clips scores, records warnings |
| Ranking Tool | `tools/ranking.py` | All formulas, benchmarks, PPI, tie-breaks, ranks (no LLM) |
| Persistence | `db/init_db.py`, `db/repository.py` | Schema, seed criteria, atomic result writes |

### Folder structure
```
app.py                  Streamlit UI
rfp_lab.ipynb           Step-by-step notebook (same run_evaluation())
agents/  tools/  db/    workflow code
data/generate_rfps.py   builds the 4 fictional PDFs in data/rfps/
tests/                  unit + UI tests (python3 -m unittest discover -s tests -t .)
scripts/                screenshot capture
outputs/sample_run.json sample exported run (created by the notebook, Step 7)
```

## Setup

```bash
pip install -r requirements.txt
export OPENAI_API_KEY=sk-...        # or ANTHROPIC_API_KEY / GEMINI_API_KEY; or pick a provider and type the key in the sidebar
python3 -m db.init_db               # create db/rfp.db and seed criteria (the app also does this automatically)
streamlit run app.py
```
For the notebook: `pip install jupyterlab`, then `python3 -m jupyterlab` and open `rfp_lab.ipynb`.
Regenerate the sample proposals with `python3 data/generate_rfps.py`.

## Formulas

For each active criterion `c` with `weight_c`, `max_c`, and supplier score `s_c`:

| Metric | Formula |
|---|---|
| Absolute weighted score | `sum( s_c / max_c * weight_c )` (0-100 when weights total 100) |
| Criterion benchmark | highest validated score for `c` across suppliers in the run |
| Criterion gap | `s_c - benchmark_c` (0 for the leader, otherwise negative) |
| Relative performance % | `s_c / benchmark_c * 100`; **100 if benchmark is 0** |
| Peer Performance Index (PPI) | `sum( relative%_c * weight_c ) / sum(weight_c)` |

**Tie-break order** (stable sort, ranks assigned afterwards): 1) higher PPI, 2) earlier submission date,
3) higher experience rating, 4) supplier name ascending. Every adjacent pair gets a plain-English explanation
of which rule separated them. Values are rounded to 6 decimals before sorting so float noise cannot change order.

## Validation behaviour

| Situation | Result |
|---|---|
| Reply is wrapped in code fences or prose | JSON extracted |
| Reply is not JSON / empty | Supplier kept, all criteria 0, `evaluation_failed`, warning |
| Missing criterion | Scored 0, warning |
| Score out of range, negative | Clipped to `[0, max_score]` (max from the database, not the LLM), warning |
| Non-numeric / NaN / boolean score | Scored 0, warning |
| Unknown, inactive or duplicate criterion id | Ignored, warning |
| Supplier name differs from the entered one | Entered name used, warning |
| PDF corrupt, encrypted or has no text | Supplier excluded, warning, others still ranked |
| LLM call fails twice | Supplier excluded, warning |
| Bad metadata (name, date, rating, file, fewer than 2 suppliers) | Rejected up front, nothing stored |

## SQLite design

- `evaluation_criteria(criterion_id, name, description, weight, max_score, is_active)`: edit this table to change the evaluation; criteria are reloaded on every run.
- `rfp_runs(rfp_run_id, created_at, status, run_json)`: `run_json` is the complete export.
- `supplier_results(rfp_run_id, supplier_name, submission_date, experience_rating, absolute_score, ppi, final_rank, result_json)`.

Results and run status are written in a single transaction (all or nothing).

## Assumptions

- Experience rating is on a **0-10** scale (`MAX_EXPERIENCE_RATING` in `agents/orchestrator.py`).
- If active weights do not total 100, scores are rescaled to 0-100 and a warning is shown.
- A run needs at least two suppliers to be meaningful; one surviving supplier still ranks, with a warning.
- Proposals longer than 60,000 characters are truncated for the LLM (with a warning).
- Proposal text is treated as untrusted; the prompt tells the model to ignore instructions inside documents.
- Scores come from an LLM, so they can vary between runs. Once validated, ranking is fully deterministic.

## Testing

```bash
python3 -m unittest discover -s tests -t .
```
44 tests cover the formulas, zero benchmarks, tie-breaks, determinism, validation repairs, PDF extraction,
prompt construction, orchestration failures, SQLite persistence and the Streamlit screens (using a fake LLM, so no API calls).

## Deploy to Streamlit Community Cloud

1. Push this folder to a GitHub repository (`.gitignore` already excludes `db/rfp.db` and secrets).
2. Go to share.streamlit.io, choose **New app**, select the repo and branch, and set the main file to `app.py`.
3. Under **Advanced settings**, pick Python 3.11 or newer.
4. Click **Deploy** and copy the public URL into the "Live app" line above.

**About the API key:** if you put `OPENAI_API_KEY` in the app's Secrets, anyone with the public link can run
evaluations on your account. For a public submission, either leave Secrets empty (users type their own key in the
sidebar) or use a key with a low spend limit. See `.streamlit/secrets.toml.example`.
The Cloud filesystem is temporary: the database is recreated and re-seeded when the app restarts.

## Screenshots

Screenshots 01, 02 and 07 need no API key. To produce 03-06 from a real run (4 OpenAI calls):

```bash
streamlit run app.py                            # terminal 1
OPENAI_API_KEY=sk-... python3 scripts/capture_screenshots.py     # terminal 2
```
This needs `pip install playwright` and Google Chrome installed.

## Demo script (one successful run and one error case)

1. Open the **Criteria** tab: five criteria, weights total 100%.
2. **Error case:** in **Supplier input** click **Load sample RFPs**, clear one supplier name, click **Evaluate suppliers**: the validation message appears and nothing runs.
3. Restore the name, enter the API key in the sidebar, click **Evaluate suppliers** and watch the progress log.
4. **Leaderboard:** rank, absolute score, PPI, submission date, experience rating.
5. **Detailed scorecard:** pick a supplier; show score, benchmark, gap, relative %, weight, and the evidence for one criterion.
6. **Run details:** show the RFP_RUN_ID, warnings, tie-break explanation, then **Download complete result (JSON)**.
7. Optional second error case: upload a non-PDF renamed to `.pdf`; that supplier is excluded with a warning while the others are ranked.
