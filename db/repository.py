"""Persistence helpers. Each write group runs in a single transaction."""
from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, List, Optional


def create_run(conn: sqlite3.Connection, run_id: str, created_at: str) -> None:
    with conn:
        conn.execute(
            "INSERT INTO rfp_runs (rfp_run_id, created_at, status, run_json) VALUES (?, ?, 'running', NULL)",
            (run_id, created_at),
        )


def finalize_run(
    conn: sqlite3.Connection,
    run_id: str,
    status: str,
    run_export: Dict[str, Any],
    supplier_rows: List[Dict[str, Any]],
) -> None:
    """Store every supplier row and the run export atomically."""
    with conn:
        for row in supplier_rows:
            conn.execute(
                "INSERT INTO supplier_results (rfp_run_id, supplier_name, submission_date, experience_rating, "
                "absolute_score, ppi, final_rank, result_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    run_id,
                    row["supplier_name"],
                    row["submission_date"],
                    row["experience_rating"],
                    row["absolute_score"],
                    row["ppi"],
                    row["final_rank"],
                    json.dumps(row, ensure_ascii=False),
                ),
            )
        conn.execute(
            "UPDATE rfp_runs SET status = ?, run_json = ? WHERE rfp_run_id = ?",
            (status, json.dumps(run_export, ensure_ascii=False), run_id),
        )


def fail_run(conn: sqlite3.Connection, run_id: str, message: str) -> None:
    payload = {"rfp_run_id": run_id, "status": "failed", "error": message}
    with conn:
        conn.execute(
            "UPDATE rfp_runs SET status = 'failed', run_json = ? WHERE rfp_run_id = ?",
            (json.dumps(payload, ensure_ascii=False), run_id),
        )


def load_run(conn: sqlite3.Connection, run_id: str) -> Optional[Dict[str, Any]]:
    row = conn.execute("SELECT run_json FROM rfp_runs WHERE rfp_run_id = ?", (run_id,)).fetchone()
    if row is None or row["run_json"] is None:
        return None
    return json.loads(row["run_json"])
